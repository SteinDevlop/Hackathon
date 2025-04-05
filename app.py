from flask import Flask, request, jsonify, g, render_template
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps
import os

app = Flask(__name__)  # Crea la aplicación Flask
app.config['SECRET_KEY'] = 'tu_clave_secreta'  # Cambiar en producción
DATABASE = 'estudiantes.db'  # Nombre de la base de datos
app.config['DATABASE'] = DATABASE  # Configura la base de datos

@app.route('/')  # Ruta principal
def home():
    return render_template('index.html')  # Renderiza el HTML

def main():
    try:
        port = int(os.environ.get('PORT',5000))
        app.run(debug=True, host='0.0.0.0', port=port)
    
    except Exception as e:
        print(f"Error al inicar la aplicacion: {e}")

if __name__ == '__main__':
    app.run(debug=True)  # Ejecuta la app en modo desarrollo


# Funciones para la base de datos
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

# Decorador para verificar token
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
            
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
            
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT * FROM usuarios WHERE id = ?', (data['user_id'],))
            current_user = cursor.fetchone()
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
            
        return f(current_user, *args, **kwargs)
    
    return decorated

# Rutas para usuarios
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password') or not data.get('username'):
        return jsonify({'message': 'Datos incompletos'}), 400
        
    db = get_db()
    cursor = db.cursor()
    
    # Verificar si el usuario ya existe
    cursor.execute('SELECT * FROM usuarios WHERE email = ?', (data['email'],))
    if cursor.fetchone():
        return jsonify({'message': 'El usuario ya existe con este email'}), 400
    
    cursor.execute('SELECT * FROM usuarios WHERE username = ?', (data['username'],))
    if cursor.fetchone():
        return jsonify({'message': 'El nombre de usuario ya está en uso'}), 400
        
    # Crear nuevo usuario
    hashed_password = generate_password_hash(data['password'], method='pbkdf2:sha256')
    
    cursor.execute(
        'INSERT INTO usuarios (email, username, password, is_active, created_at) VALUES (?, ?, ?, ?, ?)',
        (data['email'], data['username'], hashed_password, 1, datetime.datetime.now())
    )
    db.commit()
    
    return jsonify({'message': 'Usuario registrado exitosamente'}), 201

@app.route('/login', methods=['POST'])
def login():
    auth = request.get_json()
    
    if not auth or not auth.get('email') or not auth.get('password'):
        return jsonify({'message': 'No se pudo verificar'}), 401
        
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT * FROM usuarios WHERE email = ?', (auth['email'],))
    user = cursor.fetchone()
    
    if not user:
        return jsonify({'message': 'No se pudo verificar'}), 401
        
    if check_password_hash(user['password'], auth['password']):
        token = jwt.encode({
            'user_id': user['id'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        
        return jsonify({'token': token})
    
    return jsonify({'message': 'No se pudo verificar'}), 401

@app.route('/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    return jsonify({
        'id': current_user['id'],
        'email': current_user['email'],
        'username': current_user['username']
    })

# Rutas para estudiantes
@app.route('/students', methods=['POST'])
@token_required
def create_student(current_user):
    data = request.get_json()
    
    if not data:
        return jsonify({'message': 'No hay datos'}), 400
        
    required_fields = ['first_name', 'last_name', 'identity_document', 'address', 'university']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Falta el campo {field}'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    # Verificar si ya existe un estudiante con el mismo documento
    cursor.execute('SELECT * FROM estudiantes WHERE identity_document = ?', (data['identity_document'],))
    if cursor.fetchone():
        return jsonify({'message': 'Ya existe un estudiante con este documento de identidad'}), 400
    
    # Campos opcionales
    faculty = data.get('faculty', '')
    major = data.get('major', '')
    semester = data.get('semester', 0)
    
    cursor.execute(
        '''INSERT INTO estudiantes (first_name, last_name, identity_document, address, university, 
        faculty, major, semester, registration_date, owner_id) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            data['first_name'], data['last_name'], data['identity_document'], data['address'], 
            data['university'], faculty, major, semester, datetime.datetime.now(), current_user['id']
        )
    )
    db.commit()
    
    return jsonify({'message': 'Estudiante registrado exitosamente'}), 201

@app.route('/students', methods=['GET'])
@token_required
def get_all_students(current_user):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT * FROM estudiantes WHERE owner_id = ?', (current_user['id'],))
    students = cursor.fetchall()
    
    output = []
    for student in students:
        student_data = {}
        student_data['id'] = student['id']
        student_data['first_name'] = student['first_name']
        student_data['last_name'] = student['last_name']
        student_data['identity_document'] = student['identity_document']
        student_data['address'] = student['address']
        student_data['university'] = student['university']
        student_data['faculty'] = student['faculty']
        student_data['major'] = student['major']
        student_data['semester'] = student['semester']
        output.append(student_data)
    
    return jsonify({'students': output})

@app.route('/students/<student_id>', methods=['GET'])
@token_required
def get_one_student(current_user, student_id):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT * FROM estudiantes WHERE id = ? AND owner_id = ?', (student_id, current_user['id']))
    student = cursor.fetchone()
    
    if not student:
        return jsonify({'message': 'No se encontró el estudiante'}), 404
    
    student_data = {}
    student_data['id'] = student['id']
    student_data['first_name'] = student['first_name']
    student_data['last_name'] = student['last_name']
    student_data['identity_document'] = student['identity_document']
    student_data['address'] = student['address']
    student_data['university'] = student['university']
    student_data['faculty'] = student['faculty']
    student_data['major'] = student['major']
    student_data['semester'] = student['semester']
    
    return jsonify({'student': student_data})

@app.route('/students/<student_id>', methods=['PUT'])
@token_required
def update_student(current_user, student_id):
    data = request.get_json()
    
    if not data:
        return jsonify({'message': 'No hay datos para actualizar'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    # Verificar si el estudiante existe y pertenece al usuario
    cursor.execute('SELECT * FROM estudiantes WHERE id = ? AND owner_id = ?', (student_id, current_user['id']))
    student = cursor.fetchone()
    
    if not student:
        return jsonify({'message': 'No se encontró el estudiante'}), 404
    
    # Actualizar campos
    fields = ['first_name', 'last_name', 'identity_document', 'address', 'university', 'faculty', 'major', 'semester']
    update_data = []
    placeholders = []
    
    for field in fields:
        if field in data:
            update_data.append(data[field])
            placeholders.append(f"{field} = ?")
    
    if not placeholders:
        return jsonify({'message': 'No hay campos para actualizar'}), 400
    
    query = f"UPDATE estudiantes SET {', '.join(placeholders)} WHERE id = ? AND owner_id = ?"
    update_data.append(student_id)
    update_data.append(current_user['id'])
    
    cursor.execute(query, tuple(update_data))
    db.commit()
    
    return jsonify({'message': 'Estudiante actualizado exitosamente'})

@app.route('/students/<student_id>', methods=['DELETE'])
@token_required
def delete_student(current_user, student_id):
    db = get_db()
    cursor = db.cursor()
    
    # Verificar si el estudiante existe y pertenece al usuario
    cursor.execute('SELECT * FROM estudiantes WHERE id = ? AND owner_id = ?', (student_id, current_user['id']))
    student = cursor.fetchone()
    
    if not student:
        return jsonify({'message': 'No se encontró el estudiante'}), 404
    
    cursor.execute('DELETE FROM estudiantes WHERE id = ? AND owner_id = ?', (student_id, current_user['id']))
    db.commit()
    
    return jsonify({'message': 'Estudiante eliminado exitosamente'})

@app.route('/')
def index():
    return jsonify({'message': 'Bienvenido al Sistema de Gestión de Estudiantes'})

if __name__ == '__main__':
    app.run(debug=True)