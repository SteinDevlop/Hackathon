# Creando las funciones para el backend
from flask import Flask, request, jsonify, g, render_template
import sqlite3
import os

app = Flask(__name__)
# Configuración de la clave secreta (puedes agregar más configuraciones si es necesario)
app.config['SECRET_KEY'] = 'tu_clave_secreta'
DATABASE = 'estudiante.db'
app.config['DATABASE'] = DATABASE

# Función para obtener la conexión a la base de datos
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

# Cierre de la conexión al final del request
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Función para inicializar la base de datos (ejecuta el schema.sql)
def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

# Ruta para mostrar la página principal (por ejemplo, un formulario de ingreso)
@app.route('/')
def home():
    return render_template('index.html')

# 1. Función/Endpoint para agregar una persona
@app.route('/add_person', methods=['POST'])
def add_person():
    """
    Se espera un JSON con la siguiente estructura:
    {
        "persona": {
            "ID": <opcional si se quiere asignar manualmente>,
            "Nombre": "Nombre de la persona",
            "Apellido": "Apellido",
            "TipoID": <ID existente en TipoDoc>,
            "NumeroID": "Número de documento",
            "TelefonoCelular": "Celular",
            "SexoBiologico": "Masculino/Femenino/..."
        },
        "info": {
            "ID_Barrio": <ID del barrio>,
            "Direccion": "Dirección exacta"
        }
    }
    """
    data = request.get_json()
    if not data or 'persona' not in data or 'info' not in data:
        return jsonify({'error': 'Datos incompletos'}), 400

    persona_data = data['persona']
    info_data = data['info']

    # Validar campos mínimos en la parte de persona
    required_persona = ['Nombre', 'Apellido', 'TipoID', 'NumeroID', 'TelefonoCelular', 'SexoBiologico']
    for field in required_persona:
        if field not in persona_data:
            return jsonify({'error': f'Falta el campo {field} en persona'}), 400

    # Validar campos mínimos en la parte de info
    required_info = ['ID_Barrio', 'Direccion']
    for field in required_info:
        if field not in info_data:
            return jsonify({'error': f'Falta el campo {field} en info'}), 400

    db = get_db()
    cursor = db.cursor()

    try:
        # Insertar en la tabla Persona
        cursor.execute(
            """INSERT INTO Persona (Nombre, Apellido, TipoID, NumeroID, TelefonoCelular, SexoBiologico)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (persona_data['Nombre'], persona_data['Apellido'], persona_data['TipoID'],
             persona_data['NumeroID'], persona_data['TelefonoCelular'], persona_data['SexoBiologico'])
        )
        # Obtener el ID generado para la persona
        persona_id = cursor.lastrowid

        # Insertar en la tabla Persona_Info
        cursor.execute(
            """INSERT INTO Persona_Info (ID_Persona, ID_Barrio, Direccion)
               VALUES (?, ?, ?)""",
            (persona_id, info_data['ID_Barrio'], info_data['Direccion'])
        )

        db.commit()

        return jsonify({'message': 'Persona agregada exitosamente', 'ID': persona_id}), 201

    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'error': f'Error al insertar datos: {e}'}), 500

# 2. Función/Endpoint para consultar la información de una persona
@app.route('/get_person/<int:person_id>', methods=['GET'])
def get_person(person_id):
    """
    Consulta toda la información de la persona realizando joins entre:
    - Persona
    - Persona_Info
    - Barrio (para obtener el nombre del barrio)
    - Municipio (para obtener la descripción del municipio)
    - Departamento (para obtener el nombre del departamento)
    - TipoDoc (para obtener el tipo de documento)
    """
    db = get_db()
    cursor = db.cursor()

    try:
        query = """
        SELECT P.ID, P.Nombre, P.Apellido, P.TipoID, T.tipo_documento,
               P.NumeroID, P.TelefonoCelular, P.SexoBiologico,
               PI.Direccion, PI.ID_Barrio,
               B.Nombre as Barrio, 
               M.Descripcion as Municipio,
               D.Nombre as Departamento
        FROM Persona P
        LEFT JOIN Persona_Info PI ON P.ID = PI.ID_Persona
        LEFT JOIN Barrio B ON PI.ID_Barrio = B.ID
        LEFT JOIN Municipio M ON B.ID_Municipio = M.ID
        LEFT JOIN Departamento D ON M.ID_Departamento = D.ID
        LEFT JOIN TipoDoc T ON P.TipoID = T.ID
        WHERE P.ID = ?
        """
        cursor.execute(query, (person_id,))
        row = cursor.fetchone()
        if row is None:
            return jsonify({'error': 'Persona no encontrada'}), 404

        # Convertir el resultado en un diccionario
        persona = {
            'ID': row['ID'],
            'Nombre': row['Nombre'],
            'Apellido': row['Apellido'],
            'TipoID': row['TipoID'],
            'TipoDocumento': row['tipo_documento'],
            'NumeroID': row['NumeroID'],
            'TelefonoCelular': row['TelefonoCelular'],
            'SexoBiologico': row['SexoBiologico'],
            'Direccion': row['Direccion'],
            'ID_Barrio': row['ID_Barrio'],
            'Barrio': row['Barrio'],
            'Municipio': row['Municipio'],
            'Departamento': row['Departamento']
        }

        return jsonify({'persona': persona}), 200

    except sqlite3.Error as e:
        return jsonify({'error': f'Error al consultar: {e}'}), 500

# 3. Función/Endpoint para eliminar una persona
@app.route('/delete_person/<int:person_id>', methods=['DELETE'])
def delete_person(person_id):
    """
    Se elimina la persona. Primero se puede consultar la información actual
    (en el front se podría mostrar la información junto a un botón para confirmar la eliminación).
    Aquí se asume que la eliminación se realiza mediante el método DELETE.
    """
    db = get_db()
    cursor = db.cursor()

    try:
        # Verificar que la persona exista (usamos la consulta del endpoint anterior)
        cursor.execute("SELECT * FROM Persona WHERE ID = ?", (person_id,))
        row = cursor.fetchone()
        if row is None:
            return jsonify({'error': 'Persona no encontrada'}), 404

        # Primero, eliminar de Persona_Info (por la restricción de llave foránea)
        cursor.execute("DELETE FROM Persona_Info WHERE ID_Persona = ?", (person_id,))
        # Luego, eliminar de Persona
        cursor.execute("DELETE FROM Persona WHERE ID = ?", (person_id,))

        db.commit()

        return jsonify({'message': 'Persona eliminada exitosamente'}), 200

    except sqlite3.Error as e:
        db.rollback()
        return jsonify({'error': f'Error al eliminar: {e}'}), 500

# Ejecutar la aplicación
if __name__ == '__main__':
    # Descomenta la siguiente línea si aún no has inicializado la base de datos
    # init_db()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))