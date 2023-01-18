from flask import Flask, jsonify, request
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

uri = os.getenv('URI')
user = os.getenv("USERNAMENEO")
password = os.getenv("PASSWORD")
driver = GraphDatabase.driver(uri, auth=(user, password), database="neo4j")

def get_employees(tx):
    name = request.args.get('name', type=str)
    lastName = request.args.get('lastName', type=str)
    position = request.args.get('postion', type=str)
    sort = request.args.get('sort', type=str)

    query = 'MATCH (e:Employee)'
    if(name != None or lastName != None or position != None):
        query += f" WHERE e.name = '{name}' OR e.lastName = '{lastName}' OR e.position = '{position}'"
    query += ' RETURN e'
    if(sort != None):
        query += f" ORDER BY e.{sort}"

    results = tx.run(query).data()
    employees = [{'name': result['e']['name'], 'lastName': result['e']['lastName'], 'position': result['e']['position']} for result in results]
    return employees

@app.route('/employees', methods=['GET'])
def get_employees_route():
    with driver.session() as session:
        employees = session.read_transaction(get_employees)

    res = {'employees': employees}
    return jsonify(res)

def add_employees(tx, name, lastName, position, department, role):
    query = f"MATCH (e:Employee) WHERE e.name = '{name}' AND e.lastName = '{lastName}' RETURN e"
    emoloyee_found = tx.run(query).data()

    if not emoloyee_found:
        query2 = f"CREATE (e:Employee {{name: '{name}', lastName: '{lastName}', position: '{position}'}})"
        if role == 'employee':
            query2 += f" CREATE (e)-[r:WORKS_IN]->(d:Department {{name: '{department}'}})"
        else:
            query2 += f" CREATE (e)-[r:MANAGES]->(d:Department {{name: '{department}'}})"

        tx.run(query2, name=name, lastName=lastName, position=position, department=department, role=role)
        return True
    
    return False

@app.route('/employees', methods=['POST'])
def add_employees_route():
    name = request.json['name']
    lastName = request.json['lastName']
    position = request.json['position']
    department = request.json['department']
    role = request.json['role']
    if(name == '' or lastName == '' or position == '' or department == '' or role == ''):
        return jsonify('Fill required information'), 400

    with driver.session() as session:
        isAdded = session.execute_write(add_employees, name, lastName, position, department, role)
    
    if isAdded == False:
        return jsonify('Employee with that name and lastName already exists')
    
    return jsonify('Employee added')

def update_employees(tx, id, name, lastName, position, department, role):
    query = f"MATCH (e:Employee) WHERE ID(e) = '{id}' RETURN e"
    query_find_role = f"MATCH (e:Employee)-[r]->(d:Department) WHERE ID(e) = '{id}' RETURN type(r)"
    employee_found = tx.run(query, id=id).data()
    find_role = tx.run(query_find_role, id=id).data()

    if not employee_found:
        return False

    if(name != ""):
        query_name = f"MATCH (e:Employee) WHERE ID(e) = '{id}' SET e.name='{name}'"
        tx.run(query_name, id=id, name=name)
    if(lastName != ""):
        query_lastName = f"MATCH (e:Employee) WHERE ID(e) = '{id}' SET e.lastName='{lastName}'"
        tx.run(query_lastName, id=id, lastName=lastName)
    if(position != ""):
        query_position = f"MATCH (e:Employee) WHERE ID(e) = '{id}' SET e.position='{position}'"
        tx.run(query_position, id=id, position=position)
    if(department != ""):
        query_d_relation = f"MATCH (e:Employee)-[r:]->(d:Department) WHERE ID(e) = '{id}' DELETE r"
        query_department = f"MATCH (e:Employee) MATCH (d:Department) WHERE ID(e) = '{id}' and d.name = {department} CREATE (e)-[r:{find_role[0]['type(r)']}]"
        tx.run(query_d_relation, id=id)
        tx.run(query_department, id=id, department=department, find_role=find_role)
    if(role != ''):
        query_role = f"MATCH (e:Employee)-[r:{find_role}]->(d:Department) WHERE ID(e) = '{id}' CREATE (e)-[r2:{role}]->(d) SET r2 = r WITH r DELETE r"
        tx.run(query_role, find_role=find_role, id=id, role=role)
    
    return True

@app.route('/employees/<string:id>', methods=['PUT'])
def update_employees_route(id):
    name = request.json['name']
    lastName = request.json['lastName']
    position = request.json['position']
    department = request.json['department']
    role = request.json['role']

    with driver.session() as session:
        isUpdated = session.execute_write(update_employees, id, name, lastName, position, department, role)

    if not isUpdated:
        return jsonify('Employee not found'), 404

    return jsonify('Employee has been updated')

def delete_employee(tx, id):
    query = f"MATCH (e:Employee) WHERE ID(e) = '{id}' RETURN e"
    employee_found = tx.run(query).data()

    if not employee_found:
        return False

    query_find_role_and_d = f"MATCH (e:Employee)-[r]->(d:Department) WHERE ID(e) = '{id}' RETURN type(r), d"
    role_and_department = tx.run(query_find_role_and_d).data()
    
    query_delete = f"MATCH (e: Employee) WHERE ID(e) = '{id}' DETACH DELETE e"
    tx.run(query_delete, id=id)

    if role_and_department[0]['type(r)'] == "MANAGES":
        query_delete_department = f"MATCH(d:Department) WHERE d.name = '{role_and_department[0]['d']} DETACH DELETE D'"
        tx.run(query_delete_department, role_and_department=role_and_department)
    
    return True

@app.route('/employees/<string:id>', methods=['DELETE'])
def delete_employee_route(id):
    with driver.session() as session:
        isUpdated = session.execute_write(delete_employee, id)

    if not isUpdated:
        return jsonify('Employee not found'), 404

    return jsonify('Employee has been deleted')

def get_subordinates(tx, id):
    query_find_department = f"MATCH (e:Employee)-[r:MANAGES]->(d:Department) WHERE ID(e) = '{id}' RETURN d"
    find_department = tx.run(query_find_department, id=id).data()
    if not find_department:
        return False
    
    query_subordinates = f"MATCH (e:Employee)-[r:WORKS_IN]->(d:Department) WHERE d.name = '{find_department[0]['d']['name']}' RETURN e"
    find_subordinates = tx.run(query_subordinates, find_department=find_department).data()

    subordinates = [{'name': subordinate['e']['name'], 'lastName': subordinate['e']['lastName'], 'position': subordinate['e']['position']} for subordinate in find_subordinates]

    if not subordinates:
        return False
    
    return subordinates


@app.route('/employees/<string:id>/subordinates', methods=['GET'])
def get_subordinates_route(id):
    with driver.session() as session:
        subordinates = session.read_transaction(get_subordinates, id)

    if not subordinates:
        return jsonify('Not found'), 404

    res = {'subordinates': subordinates}
    return jsonify(res)

def get_department(tx, id):
    query_department = f"MATCH (d:Department) WHERE ID(d) = '{id}' RETURN d"
    query_manager = f"MATCH (e:Employee)-[r:MANAGES]->(d:Department) WHERE ID(d) = '{id}' RETURN e"
    query_employees = f"MATCH (e:Employee)-[r:WORKS_IN]->(d:Department) WHERE ID(d) = '{id}' RETURN e"
    query_number_of_employees = f"MATCH (e:Employee)-[r:WORKS_IN]->(d:Department) WHERE ID(d) = '{id}' COUNT(e)"

    department = tx.run(query_department, id=id).data()

    if not department:
        return False

    manager = tx.run(query_manager, id=id).data()
    employees = tx.run(query_employees, id=id).data()
    number = tx.run(query_number_of_employees, id=id).data()

    info = {'department': department[0]['d'], 'manager': manager[0]['e'], 'employees': employees[0]['e'], 'numberOfEmployees': number[0]['COUNT(e)']}
    return info

@app.route('/departments/<string:id>', methods=['GET'])
def get_department_route(id):
    with driver.session() as session:
        department = session.read_transaction(get_department, id)

    if not department:
        return jsonify('Not found'), 404

    res = {'department': department}
    return jsonify(res)

def get_departments(tx):
    name = request.args.get('name', type=str)
    sort = request.args.get('sort', type=str)

    query = 'MATCH (d:Department)'
    if(name != None):
        query += f" WHERE d.name = '{name}'"
    query += ' RETURN d'
    if(sort != None):
        query += f" ORDER BY d.{sort}"

    results = tx.run(query).data()
    departments = [{'name': result['d']['name'], } for result in results]
    return departments

@app.route('/departments', methods=['GET'])
def get_departments_route():
    with driver.session() as session:
        departments = session.read_transaction(get_departments)

    if not departments:
        return jsonify('Not found any'), 404

    res = {'departments': departments}
    return jsonify(res)

def get_employees_in_department(tx, id):
    query = f"MATCH (e:Employess)-[r:WORKS_IN]->(d:Department) WHERE ID(d) = '{id}' RETURN e"
    results = tx.run(query, id=id).data()

    if not results:
        return False

    employees = [{'name': result['e']['name'], 'lastName': result['e']['lastName'], 'position': result['e']['position']} for result in results]
    return employees

@app.route('/departments/<string:id>/employees', methods=['GET'])
def get_employees_in_department_route(id):
    with driver.session() as session:
        employees = session.read_transaction(get_employees_in_department, id)
    
    if not employees:
        return jsonify('Not found'), 404

    res = {'employees': employees}
    return jsonify(res)


if __name__ == '__main__':
    app.run()