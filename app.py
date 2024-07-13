import base64
from functools import wraps
# from aifc import Error
import datetime
from io import BytesIO
import json
import secrets
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import requests
from decimal import Decimal
import numpy as np
import urllib.request
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import os
import psycopg2
import xlsxwriter
import psycopg2.extras
from sqlalchemy import create_engine
import pandas as pd
import psycopg2
from io import StringIO
from werkzeug.utils import secure_filename
import logging
from psycopg2.extras import DictCursor
from datetime import date, datetime, timedelta
import hashlib
from collections import defaultdict




load_dotenv()


app = Flask(__name__)

@app.route('/')
def main():
    return render_template('jjfj.html')


app.config['STATIC_FOLDER'] = 'static'
app.secret_key = 'gjf837nfc9ech'

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

#--------------INDEX----------------------

@app.before_request
def check_admin():
    if request.endpoint == 'managers_page':
        if 'admin_logged_in' not in session or not session['admin_logged_in']:
            return redirect(url_for('admin_page'))



def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' in session and session['admin_logged_in']:
            return f(*args, **kwargs)
        else:
            return redirect(url_for('admin_page'))
    return decorated_function

@app.route('/managers')
@admin_login_required
def managers_page():
    return render_template('managers.html')

def get_database_connection():
    database_url = os.environ.get('DATABASE_URL')
    connection = psycopg2.connect(database_url)
    return connection

@app.route('/admin')
def admin_page():
    if 'admin_logged_in' in session and session['admin_logged_in']:
        return redirect(url_for('admin_dashboard'))
    else:
        return render_template('admin_login.html')
    
@app.route('/admin/dashboard')
@admin_login_required
def admin_dashboard():
    return render_template('index.html')

@app.route('/admin/login', methods=['POST', 'GET'])
def admin_login():
    login = request.form['login']
    password = request.form['password']
    print("login", login)
    print("password", password)
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM admin WHERE login = %s AND password = %s", (login, password))
        admin = cursor.fetchone()

        if admin:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return "Login failed. Invalid credentials."
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return "An error occurred while processing your request. Please try again later."



    




@app.route('/order-count/in-transit')

def get_orders_in_transit_count():
    user_id = request.args.get('user_id')
    if user_id is None:
        return jsonify({'error': 'User ID is missing'}), 400
    return get_orders_count_by_status(int(user_id), 1)

@app.route('/order-count/in-sorting')
def get_orders_in_sorting_count():
    user_id = request.args.get('user_id')
    if user_id is None:
        return jsonify({'error': 'User ID is missing'}), 400
    return get_orders_count_by_status(int(user_id), 2)

@app.route('/order-count/ready-for-delivery')
def get_orders_ready_for_delivery_count():
    user_id = request.args.get('user_id')
    if user_id is None:
        return jsonify({'error': 'User ID is missing'}), 400
    return get_orders_count_by_status(int(user_id), 3)

@app.route('/order-count/paid')
def get_paid_orders_count():
    user_id = request.args.get('user_id')
    if user_id is None:
        return jsonify({'error': 'User ID is missing'}), 400
    return get_orders_count_by_status(int(user_id), 4)

def get_orders_count_by_status(user_id, status_id):
    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute('''
            SELECT COUNT(*)
            FROM "Order"
            WHERE order_status_id = %s AND user_id = %s
        ''', (status_id, user_id))

        count = cursor.fetchone()[0]

        cursor.close()
        connection.close()

        return jsonify({'count': count})
    except Error as e:
        print(f'Database error: {e}')
        return jsonify({'error': 'Failed to retrieve order count'}), 500

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
@app.route('/upload_data_avia', methods=['POST'])

def upload_data_to_db():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не найден'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        logging.error(f'Ошибка при чтении Excel файла: {e}')
        return jsonify({'error': 'Ошибка при чтении Excel файла'}), 500

    try:
        selected_columns = ['data_send_from_china', 'user_id', 'track_code', 'order_status_id']
        df = df[selected_columns]
        df['order_type_id'] = 1  # Добавляем столбец order_type_id со значением 2 для всех записей
    except Exception as e:
        logging.error(f'Ошибка при выборе столбцов: {e}')
        return jsonify({'error': 'Ошибка при выборе столбцов'}), 500

    try:
        # Преобразование значений столбца user_id к целочисленному типу
        df['user_id'] = df['user_id'].astype('Int64')
    except Exception as e:
        logging.error(f'Ошибка при преобразовании типа данных в столбце user_id: {e}')
        return jsonify({'error': 'Ошибка при обработке данных'}), 500

    try:
        buffer = StringIO()
        df.to_csv(buffer, index=False, header=False, sep='\t')
        buffer.seek(0)
    except Exception as e:
        error_message = f'Ошибка при подготовке данных для загрузки: {str(e)}'
        logging.error(error_message)
        return jsonify({'error': error_message}), 500

    try:
        existing_track_codes = set()
        connection = get_database_connection()
        cursor = connection.cursor()

        # Получаем множество трек-кодов, которые уже есть в таблице
        cursor.execute("SELECT track_code FROM \"Order\"")
        existing_track_codes = {row[0] for row in cursor.fetchall()}

        # Фильтруем данные по трек-кодам, которых еще нет в таблице
        df_filtered = df[~df['track_code'].isin(existing_track_codes)]

        # Если после фильтрации не осталось данных, возвращаем сообщение об успехе
        if df_filtered.empty:
            return jsonify({'message': 'Новых данных для загрузки нет'}), 200

        # Создаем новый буфер с отфильтрованными данными
        buffer_filtered = StringIO()
        df_filtered.to_csv(buffer_filtered, index=False, header=False, sep='\t')
        buffer_filtered.seek(0)

        # Загружаем новые данные в базу данных
        cursor.copy_expert("COPY \"Order\" (data_send_from_china, user_id, track_code, order_status_id, order_type_id) FROM STDIN WITH CSV DELIMITER '\t'", buffer_filtered)
        connection.commit()

    except Exception as e:
        error_message = f'Ошибка при загрузке данных в базу данных: {str(e)}'
        logging.error(error_message)
        return jsonify({'error': error_message}), 500

    return jsonify({'message': 'Данные успешно загружены'}), 200


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
@app.route('/upload_data_land', methods=['POST'])
def upload_data_to_db_land():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не найден'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        logging.error(f'Ошибка при чтении Excel файла: {e}')
        return jsonify({'error': 'Ошибка при чтении Excel файла'}), 500

    try:
        selected_columns = ['data_send_from_china', 'user_id', 'track_code', 'order_status_id']
        df = df[selected_columns]
        df['order_type_id'] = 2  # Добавляем столбец order_type_id со значением 2 для всех записей
    except Exception as e:
        logging.error(f'Ошибка при выборе столбцов: {e}')
        return jsonify({'error': 'Ошибка при выборе столбцов'}), 500

    try:
        # Преобразование значений столбца user_id к целочисленному типу
        df['user_id'] = df['user_id'].astype('Int64')
        # Преобразование трек-кодов в строки и удаление пробелов по краям
        df['track_code'] = df['track_code'].astype(str).str.strip()
    except Exception as e:
        logging.error(f'Ошибка при преобразовании типа данных в столбце user_id или track_code: {e}')
        return jsonify({'error': 'Ошибка при обработке данных'}), 500

    try:
        buffer = StringIO()
        df.to_csv(buffer, index=False, header=False, sep='\t')
        buffer.seek(0)
    except Exception as e:
        error_message = f'Ошибка при подготовке данных для загрузки: {str(e)}'
        logging.error(error_message)
        return jsonify({'error': error_message}), 500

    try:
        connection = get_database_connection()
        cursor = connection.cursor()

        # Получаем множество трек-кодов, которые уже есть в таблице
        cursor.execute("SELECT track_code FROM \"Order\"")
        existing_track_codes = {row[0].strip() for row in cursor.fetchall()}
        logging.debug(f'Существующие трек-коды: {existing_track_codes}')

        # Преобразование трек-кодов в строки и удаление пробелов по краям в DataFrame
        df['track_code'] = df['track_code'].astype(str).str.strip()

        # Фильтруем данные по трек-кодам, которых еще нет в таблице
        df_filtered = df[~df['track_code'].isin(existing_track_codes)]
        logging.debug(f'Новые данные для загрузки: {df_filtered}')

        # Если после фильтрации не осталось данных, возвращаем сообщение об успехе
        if df_filtered.empty:
            logging.info('Новых данных для загрузки нет')
            return jsonify({'message': 'Новых данных для загрузки нет'}), 200

        # Создаем новый буфер с отфильтрованными данными
        buffer_filtered = StringIO()
        df_filtered.to_csv(buffer_filtered, index=False, header=False, sep='\t')
        buffer_filtered.seek(0)

        # Загружаем новые данные в базу данных, используя SQL-запрос с условием отсутствия трек-кода в базе
        cursor.copy_expert("COPY \"Order\" (data_send_from_china, user_id, track_code, order_status_id, order_type_id) FROM STDIN WITH CSV DELIMITER '\t'", buffer_filtered)
        connection.commit()

    except Exception as e:
        error_message = f'Ошибка при загрузке данных в базу данных: {str(e)}'
        logging.error(error_message)
        return jsonify({'error': error_message}), 500

    finally:
        cursor.close()
        connection.close()

    return jsonify({'message': 'Данные успешно загружены'}), 200



logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

@app.route('/upload_data_p', methods=['POST'])
@admin_login_required
def upload_data_to_db_p():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не найден'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        logging.error(f'Ошибка при чтении Excel файла: {e}')
        return jsonify({'error': 'Ошибка при чтении Excel файла'}), 500

    try:
        selected_columns = ['data_send_from_china', 'user_id', 'track_code', 'order_status_id', 'item_id']
        df = df[selected_columns]
    except Exception as e:
        logging.error(f'Ошибка при выборе столбцов: {e}')
        return jsonify({'error': 'Ошибка при выборе столбцов'}), 500

    try:
        # Преобразование значений столбца user_id к целочисленному типу
        df['user_id'] = df['user_id'].astype('Int64')
    except Exception as e:
        logging.error(f'Ошибка при преобразовании типа данных в столбце user_id: {e}')
        return jsonify({'error': 'Ошибка при обработке данных'}), 500

    try:
        buffer = StringIO()
        df.to_csv(buffer, index=False, header=False, sep='\t')
        buffer.seek(0)
    except Exception as e:
        error_message = f'Ошибка при подготовке данных для загрузки: {str(e)}'
        logging.error(error_message)
        return jsonify({'error': error_message}), 500

    try:
        existing_track_codes = set()
        connection = get_database_connection()
        cursor = connection.cursor()

        # Получаем множество трек-кодов, которые уже есть в таблице
        cursor.execute("SELECT track_code FROM \"Order\"")
        existing_track_codes = {row[0] for row in cursor.fetchall()}

        # Фильтруем данные по трек-кодам, которых еще нет в таблице
        df_filtered = df[~df['track_code'].isin(existing_track_codes)]

        # Если после фильтрации не осталось данных, возвращаем сообщение об успехе
        if df_filtered.empty:
            return jsonify({'message': 'Новых данных для загрузки нет'}), 200

        # Создаем новый буфер с отфильтрованными данными
        buffer_filtered = StringIO()
        df_filtered.to_csv(buffer_filtered, index=False, header=False, sep='\t')
        buffer_filtered.seek(0)

        # Загружаем новые данные в базу данных
        cursor.copy_expert("COPY \"Order\" (data_send_from_china, user_id, track_code, order_status_id, item_id) FROM STDIN WITH CSV DELIMITER '\t'", buffer_filtered)
        connection.commit()

    except Exception as e:
        error_message = f'Ошибка при загрузке данных в базу данных: {str(e)}'
        logging.error(error_message)
        return jsonify({'error': error_message}), 500

    return jsonify({'message': 'Данные успешно загружены'}), 200

#-----------------------SORTING----------------------------------------

@app.route('/sort_reg')
@admin_login_required
def sort_reg_page():
    return render_template("sort_reg.html")



@app.route('/update_order_status5', methods=['POST'])
@admin_login_required
def update_order_status5():
    data = request.json
    track_code = data.get('track_code')
    city_id = data.get('city_id')

    # Логирование входных данных
    app.logger.info(f'Received data: track_code={track_code}, city_id={city_id}')

    # Проверка на наличие необходимых данных
    if not track_code or not city_id:
        app.logger.error('Missing track_code or city_id')
        return jsonify({"error": "Трек-код и идентификатор региона обязательны"}), 400

    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Извлечение user_id из таблицы "Order"
        cur.execute('SELECT user_id FROM "Order" WHERE track_code = %s', (track_code,))
        user_id = cur.fetchone()
        if not user_id:
            app.logger.error(f'Заказ с трек-кодом {track_code} не найден')
            return jsonify({"error": "Заказ с данным трек-кодом не найден"}), 404
        user_id = user_id[0]

        # Извлечение city_id из таблицы "User"
        cur.execute('SELECT city_id FROM "User" WHERE id = %s', (user_id,))
        order_city_id = cur.fetchone()
        if not order_city_id:
            app.logger.error(f'Пользователь с ID {user_id} не найден')
            return jsonify({"error": "Пользователь не найден"}), 404
        order_city_id = order_city_id[0]

        # Проверка региона заказа
        if order_city_id != int(city_id):
            app.logger.error(f'Город заказа {order_city_id} не совпадает с выбранным городом {city_id}')
            return jsonify({"error": "Заказ не принадлежит выбранному региону"}), 400

        # Обновление статуса заказа на 5 и установка города заказа
        cur.execute('''
            UPDATE "Order"
            SET order_status_id = 5,
                date_sent_from_bishkek = %s,
                city_id = %s
            WHERE track_code = %s
        ''', (date.today(), city_id, track_code))
        conn.commit()

        return jsonify({"success": f"Статус заказа с трек-кодом {track_code} успешно изменен на 5."}), 200
    except psycopg2.Error as e:
        app.logger.error(f'Ошибка при обновлении статуса заказа: {e}')
        return jsonify({"error": f"Ошибка при обновлении статуса заказа: {e}"}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

def get_track_codes_by_date_and_region(selected_date, selected_region):
    # Подключение к базе данных и выполнение запроса
    conn = get_database_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT track_code
        FROM "Order"
        WHERE date_sent_from_bishkek = %s AND city_id = %s
    ''', (selected_date, selected_region))
    track_codes = cur.fetchall()
    conn.close()
    
    return [code[0] for code in track_codes]


@app.route('/generate_excel', methods=['POST'])
def generate_excel():
    # Получение данных из формы
    selected_date = request.form['selected_date']
    selected_region = request.form['selected_region']
    
    # Получение трек-кодов по выбранной дате и региону
    track_codes = get_track_codes_by_date_and_region(selected_date, selected_region)
    
    # Создание DataFrame с трек-кодами
    df = pd.DataFrame({'Track Code': track_codes})
    
    # Создание Excel-файла
    file_name = f'track_codes_{selected_date}_{selected_region}.xlsx'
    df.to_excel(file_name, index=False)
    
    # Отправка файла как вложения в HTTP-ответе
    return send_file(file_name, as_attachment=True)
@app.route('/regions_report')
@admin_login_required
def regions_report():
    return render_template("regions_report.html")

@app.route('/get_orders_by_city/<int:city_id>', methods=['GET'])
def get_orders_by_city(city_id):
    conn = get_database_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT date_sent_from_bishkek, COUNT(*)
        FROM "Order"
        WHERE city_id = %s AND date_sent_from_bishkek IS NOT NULL
        GROUP BY date_sent_from_bishkek
        ORDER BY date_sent_from_bishkek
    ''', (city_id,))
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{'date': order[0].strftime('%Y-%m-%d'), 'count': order[1]} for order in orders])

def login_required_for_sorting(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session and 'punkt_manager_id' not in session and 'manager_id' not in session:
            return redirect(url_for('admin_login'))  # Перенаправление на страницу входа администратора
        return f(*args, **kwargs)
    return decorated_function

@app.route('/sorting')
@login_required_for_sorting
def sorting_page():
    return render_template('sorting.html')

@app.route('/get_order_details', methods=['POST'])
@login_required_for_sorting
def get_order_details():
    track_code = request.form.get('trackCode')
    if not track_code:
        logging.error('Трек-код не предоставлен')
        return jsonify({'error': 'Трек-код не предоставлен'}), 400

    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT o.data_send_from_china, o.user_id, o.track_code, os.name AS order_status,
                   u.user_tarif, u.user_tarif_avia, u.city_id, o.massa, o.po_obyome, o.comment, o.sort_date, o.order_type_id
            FROM "Order" o
            JOIN "User" u ON o.user_id = u.id
            JOIN Order_status os ON o.order_status_id = os.id
            WHERE o.track_code = %s
        ''', (track_code,))

        order = cur.fetchone()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    if order:
        city_id = order['city_id']
        city_name = None
        try:
            conn = get_database_connection()
            cur = conn.cursor(cursor_factory=DictCursor)

            cur.execute('SELECT name FROM City WHERE id = %s', (city_id,))
            city = cur.fetchone()
            if city:
                city_name = city['name']
        except Exception as e:
            logging.error(f'Ошибка при запросе к базе данных для получения информации о городе: {e}')
        finally:
            cur.close()
            conn.close()

        if order['po_obyome']:
            price = calculate_price_by_volume(order['massa'], order['dlina'], order['glubina'], order['shirina'])
        else:
            if order['order_type_id'] == 1:
                user_tarif = order['user_tarif_avia'] if order['user_tarif_avia'] else Decimal('0.0')
            else:
                user_tarif = order['user_tarif'] if order['user_tarif'] else Decimal('0.0')

            massa = order['massa'] if order['massa'] else Decimal('0.0')
            price = user_tarif * massa

        massa = order['massa'] if order['massa'] else 'Not specified'
        order_details = {
            'data_send_from_china': order['data_send_from_china'].strftime('%Y-%m-%d') if order['data_send_from_china'] else 'Not specified',
            'user_id': order['user_id'],
            'track_code': order['track_code'],
            'order_status': order['order_status'],
            'city': city_name,
            'massa': massa,
            'price': str(price),
            'comment': order['comment'],
            'sort_date': order['sort_date']
        }
        return jsonify(order_details)
    else:
        logging.error('Заказ с таким трек-кодом не найден')
        return jsonify({'error': 'Заказ с таким трек-кодом не найден'}), 404



def calculate_price_by_volume(massa, dlina, glubina, shirina):
    volume = dlina * glubina * shirina
    price_per_cubic_meter = 100
    price = volume * price_per_cubic_meter
    return price

from decimal import Decimal

from decimal import Decimal

@app.route('/save_order_details', methods=['POST'])
def save_order_details():
    data = request.json
    track_code = data.get('track_code')
    user_id = data.get('user_id')
    massa = float(data.get('massa'))
    po_obyome = data.get('po_obyome')
    dlina = data.get('dlina')
    shirina = data.get('shirina')
    glubina = data.get('glubina')
    obreshetka_sum = float(data.get('obreshetka_sum')) if data.get('obreshetka_sum') else 0  # Проверяем, передано ли значение суммы обрешетки
    comment = data.get('comment')
    user_tarif = Decimal(data.get('user_tarif')) if data.get('user_tarif') else Decimal('0.0')
    china_tariff = Decimal(data.get('china_tariff')) if data.get('china_tariff') else Decimal('0.0')

    if not track_code:
        logging.error('Трек-код не предоставлен')
        return jsonify({'error': 'Трек-код не предоставлен'}), 400

    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Получаем данные пользователя и типа заказа (order_type_id)
        cur.execute('''
            SELECT u.city_id, u.user_tarif, u.user_tarif_avia, u.punkt_id, u.region_id, o.order_type_id
            FROM "User" u
            JOIN "Order" o ON u.id = o.user_id
            WHERE u.id = %s AND o.track_code = %s
        ''', (user_id, track_code))
        user_data = cur.fetchone()
        if not user_data:
            logging.error(f'Пользователь или заказ с указанным ID/трек-кодом не найден для user_id={user_id}, track_code={track_code}')
            return jsonify({'error': 'Пользователь или заказ с указанным ID/трек-кодом не найден'}), 400

        city_id = user_data[0]
        punkt_id = user_data[3]
        region_id = user_data[4]

        # Определяем тариф в зависимости от типа заказа
        if user_data[5] == 1 and user_data[2]:  # Если тип заказа 1 и есть тариф авиа
            user_tarif = user_data[2]
        elif user_data[1]:
            user_tarif = user_data[1]

        dlina = float(dlina) if dlina else None
        shirina = float(shirina) if shirina else None
        glubina = float(glubina) if glubina else None

        if po_obyome:
            price = calculate_price_by_volume(massa, dlina, glubina, shirina)
        else:
            price = user_tarif * Decimal(massa)

        # Учитываем сумму обрешетки, если она указана
        price += obreshetka_sum

        # Рассчитываем скидку, если применимо
        if user_data[5] == 1 and user_data[2]:  # Если тип заказа 1 и есть тариф авиа
            discount_amount = user_data[2] * Decimal(massa) - price
        else:
            discount_amount = 0

        amount = round(price)

        # Обновляем данные заказа, включая china_tariff, punkt_id и region_id
        cur.execute('''
            UPDATE "Order"
            SET user_id=%s, user_tarif=%s, china_tariff=%s, city_id=%s, punkt_id=%s, region=%s, massa=%s, po_obyome=%s, dlina=%s, shirina=%s, glubina=%s, amount=%s, discount_amount=%s, comment=%s, order_status_id=2, sort_date=CURRENT_TIMESTAMP
            WHERE track_code=%s
        ''', (user_id, user_tarif, china_tariff, city_id, punkt_id, region_id, massa, po_obyome, dlina, shirina, glubina, amount, discount_amount, comment, track_code))

        conn.commit()

        # В случае успеха возвращаем сообщение о успешном обновлении данных заказа
        return jsonify({'success': 'Данные заказа успешно обновлены'})

    except Exception as e:
        logging.error(f'Ошибка при обновлении данных заказа: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

    finally:
        if 'cur' in locals() and cur:
            cur.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/finish_sorting', methods=['POST'])

def finish_sorting():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('UPDATE "Order" SET order_status_id = 3 WHERE order_status_id = 2 RETURNING id')
        affected_rows = cur.rowcount  

        conn.commit()
        return jsonify({'message': f'{affected_rows} заказов отсортировано'})
    except Exception as e:
        logging.error(f'Ошибка при обновлении статусов заказов: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()


#-------------orders-----------------------

@app.route('/get_all_orders_p', methods=['GET'])
@admin_login_required
def get_all_orders_p():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                o.id,
                o.data_send_from_china, 
                o.track_code, 
                os.name AS order_status, 
                o.massa, 
                o.comment, 
                o.sort_date, 
                o.amount,
                o.payment_status,
                u.id as user_id,
                u.name || ' ' || u.surname AS client_fio, 
                c.name AS city_name,
                ct.phone_num, 
                o.discount_amount,
                i.name AS item_name,
                o.quantity,
                o.predoplata
            FROM "Order" o
            LEFT JOIN Order_status os ON o.order_status_id = os.id
            LEFT JOIN "User" u ON o.user_id = u.id
            LEFT JOIN City c ON u.city_id = c.id
            LEFT JOIN Contact ct ON u.id = ct.user_id
            LEFT JOIN Item i ON o.item_id = i.id
            WHERE o.item_id IS NOT NULL;
        ''')

        orders = cur.fetchall()
        
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    orders_data = []
    for order in orders:
        debt_amount = float(order['amount']) - float(order['predoplata'])
        order_details = {
            'id': order['id'],
            'data_send_from_china': order['data_send_from_china'].strftime('%Y-%m-%d') if order['data_send_from_china'] else 'Не указано',
            'track_code': order['track_code'],
            'order_status': order['order_status'],
            'massa': order['massa'],
            'comment': order['comment'],
            'client_fio': order['client_fio'],
            'user_id':order['user_id'],
            'city_name': order['city_name'],
            'phone_num': order['phone_num'],
            'sort_date': order['sort_date'].strftime('%Y-%m-%d %H:%M:%S') if order['sort_date'] else 'Не указано',
            'amount': str(order['amount']),
            'discount_amount': str(order['discount_amount']),
            'item_name': order['item_name'],
            'quantity': order['quantity'],
            'prepayment': str(order['predoplata']),
            'debt_amount': str(debt_amount)
        }
        orders_data.append(order_details)

    return jsonify(orders_data)

@app.route('/orders_p')
@admin_login_required
def orders_page_p():
    return render_template('purchase.html')

@app.route('/get_item_price/<item_code>', methods=['GET'])
def get_item_price(item_code):
    try:
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('SELECT final_price FROM Item WHERE id = %s', (item_code,))
        price = cur.fetchone()[0]
        return jsonify({'price': price})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/add_buyout', methods=['POST'])
def add_buyout():
    try:
        client_code = request.form['clientCode']
        item_code = request.form['itemCode']
        city_id = request.form['cityId']
        track_code = request.form['trackCode']
        comment = request.form['comment']
        quantity = int(request.form['quantity'])
        prepayment = float(request.form['prepayment'])
        order_status_id=1
        
        # Устанавливаем текущую дату
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = get_database_connection()
        cur = conn.cursor()

        # Получаем цену товара
        cur.execute('SELECT final_price FROM Item WHERE id = %s', (item_code,))
        item_price = cur.fetchone()[0]
        total_amount = item_price * quantity

        # Добавляем запись в таблицу заказов с использованием текущей даты
        cur.execute('''
            INSERT INTO "Order" (user_id, item_id, city_id, track_code, comment, quantity, amount, data_send_from_china, predoplata, order_status_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (client_code, item_code, city_id, track_code, comment, quantity, total_amount, current_date, prepayment, order_status_id))

        
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print({'error': str(e)})
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/top_10_items_data', methods=['GET'])
def top_10_items_data():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Запрос для получения данных о топ-10 товарах по марже и количеству
        cur.execute('''
            SELECT 
                i.name AS item_name,
                SUM(o.quantity) AS total_quantity,
                SUM(o.quantity * i.total_margin) AS total_margin
            FROM "Order" o
            LEFT JOIN Item i ON o.item_id = i.id
            GROUP BY i.name, i.total_margin
            ORDER BY total_margin DESC
            LIMIT 10;
        ''')

        rows = cur.fetchall()
        top_10_items = []
        for row in rows:
            item_data = {
                'item_name': row[0],
                'total_quantity': row[1],
                'total_margin': float(row[2]) if row[2] is not None else 0.0
            }
            top_10_items.append(item_data)

        return jsonify(top_10_items)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cur.close()
        conn.close()

@app.route('/dashboard_data', methods=['GET'])
@admin_login_required
def dashboard_data():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Запрос для получения общего количества заказов
        cur.execute('SELECT COUNT(*)   FROM "Order" o WHERE o.item_id IS NOT NULL;')
        total_orders = cur.fetchone()[0]

        # Запрос для получения общей прибыли (суммы маржи по всем товарам)
        cur.execute('''
           SELECT SUM(o.quantity * i.total_margin) AS total_profit
            FROM "Order" o
            LEFT JOIN Item i ON o.item_id = i.id
            WHERE o.item_id IS NOT NULL;

        ''')
        total_profit = cur.fetchone()[0]

        if total_profit is None:
            total_profit = 0

        # Запрос для получения общей суммы долгов (сумма amount - предоплата)
        cur.execute('''
            SELECT SUM(o.amount - o.predoplata) AS total_debts
            FROM "Order" o;
        ''')
        total_debts = cur.fetchone()[0]

        if total_debts is None:
            total_debts = 0

        return jsonify({
            'totalOrders': total_orders,
            'totalProfit': float(total_profit),
            'totalDebts': float(total_debts)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cur.close()
        conn.close()

@app.route('/statvikup')
@admin_login_required
def statvikup():
    return render_template("vikupstat.html")

@app.route('/orders')
@admin_login_required
def orders_page():
    return render_template('orders.html')

@app.route('/get_all_orders', methods=['GET'])
@admin_login_required
def get_all_orders():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                o.id,
                o.data_send_from_china, 
                o.track_code, 
                os.name AS order_status, 
                o.user_tarif,
                o.massa, 
                o.comment, 
                o.sort_date, 
                o.amount,
                o.payment_status,
                u.name || ' ' || u.surname AS client_fio, 
                u.id AS user_id, 
                c.name AS city_name, 
                ct.phone_num, 
                ct.extra_phone_num, 
                ct.tg_nickname, 
                ct.email,
                o.discount_amount,
                ot.name AS order_type
            FROM "Order" o
            JOIN Order_status os ON o.order_status_id = os.id
            LEFT JOIN "User" u ON o.user_id = u.id
            LEFT JOIN City c ON u.city_id = c.id
            LEFT JOIN contact ct ON u.id = ct.user_id
            LEFT JOIN order_type ot ON o.order_type_id = ot.id;
        ''')

        orders = cur.fetchall()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    orders_data = []
    for order in orders:
        order_details = {
            'id': order['id'],
            'data_send_from_china': order['data_send_from_china'].strftime('%Y-%m-%d') if order['data_send_from_china'] else 'Не указано',
            'track_code': order['track_code'],
            'order_status': order['order_status'],
            'user_tarif': str(order['user_tarif']),
            'massa': order['massa'],
            'comment': order['comment'],
            'client_fio': order['client_fio'],
            'user_id': order['user_id'],
            'city_name': order['city_name'],
            'phone_num': order['phone_num'],
            'extra_phone_num': order['extra_phone_num'],
            'tg_nickname': order['tg_nickname'],
            'email': order['email'],
            'sort_date': order['sort_date'].strftime('%Y-%m-%d %H:%M:%S') if order['sort_date'] else 'Не указано',
            'amount': str(order['amount']),
            'discount_amount': str(order['discount_amount']),
            'payment_status': order['payment_status'],
            'order_type': order['order_type']
        }
        
        orders_data.append(order_details)

    return jsonify(orders_data)


@app.route('/update_order_user', methods=['POST'])
@admin_login_required
def update_order_user():
    data = request.json
    track_code = data.get('track_code')
    new_user_id = data.get('new_user_id')

    print(f"Received track code: {track_code}, new user ID: {new_user_id}")

    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('''
            UPDATE "Order"
            SET user_id = %s
            WHERE track_code = %s
        ''', (new_user_id, track_code))

        conn.commit()

        return jsonify({'success': True, 'message': 'Трек код в заказе успешно обновлен'})
    except Exception as e:
        conn.rollback()
        logging.error(f'Ошибка при обновлении трек кода в заказе: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

# _______________managers_______
@app.route('/get_all_managers', methods=['GET'])
@admin_login_required
def get_all_managers():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT m.id, m.name, m.surname, c.name AS city_name, m.phone_number, m.login, m.password
            FROM Manager m
            JOIN City c ON m.city_id = c.id
        ''')

        managers = cur.fetchall()
    except Exception as e:
        # Обработка ошибки подключения к базе данных
        return jsonify({'error': 'Ошибка при подключении к базе данных'}), 500
    finally:
        cur.close()
        conn.close()

    managers_data = []
    for manager in managers:
        manager_details = {
            'id': manager['id'],
            'name': manager['name'],
            'surname': manager['surname'],
            'city_name': manager['city_name'],
            'phone_number': manager['phone_number'],
            'login': manager['login'],
            'password': manager['password']
        }
        managers_data.append(manager_details)

    return jsonify(managers_data)

@app.route('/get_all_cities', methods=['GET'])
@admin_login_required
def get_all_cities():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('SELECT id, name FROM City')
        cities = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]

        return jsonify(cities)
    except Exception as e:
        return jsonify({'error': 'Ошибка при получении списка городов'}), 500
    finally:
        cur.close()
        conn.close()

# Маршрут для добавления нового менеджера
@app.route('/add_manager', methods=['POST'])
@admin_login_required
def add_manager():
    data = request.json

    name = data.get('name')
    surname = data.get('surname')
    city_id = data.get('city_id')
    phone_number = data.get('phone_number')
    login = data.get('login')
    password = data.get('password')

    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('''
            INSERT INTO Manager (name, surname, city_id, phone_number, login, password)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (name, surname, city_id, phone_number, login, password))

        conn.commit()

        return jsonify({'success': True, 'message': 'Менеджер успешно добавлен'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Ошибка при добавлении менеджера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/add_punkt_manager', methods=['POST'])
@admin_login_required
def add_punkt_manager():
    data = request.json

    name = data.get('name')
    surname = data.get('surname')
    punkt_id = data.get('city_id')
    phone_number = data.get('phone_number')
    login = data.get('login')
    password = data.get('password')
    addres=data.get('address')
    print("addres" ,addres )

    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('''
            INSERT INTO punkt_manager (name, surname, punkt_id, phone_number, login, password, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (name, surname, punkt_id, phone_number, login, password, addres))

        conn.commit()

        return jsonify({'success': True, 'message': 'Менеджер успешно добавлен'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Ошибка при добавлении менеджера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/delete_punkt_manager/<int:manager_id>', methods=['DELETE'])
@admin_login_required
def delete_punkt_manager(manager_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('DELETE FROM punkt_manager WHERE id = %s', (manager_id,))

        conn.commit()

        return jsonify({'success': True, 'message': 'Менеджер успешно удален'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Ошибка при удалении менеджера'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/get_all_punkts', methods=['GET'])
@admin_login_required
def get_all_punkts():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('SELECT id, name FROM Punkt')
        punkts = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]

        return jsonify(punkts)
    except Exception as e:
        return jsonify({'error': 'Ошибка при получении списка пунктов'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/get_all_punkt_managers', methods=['GET'])
@admin_login_required
def get_all_punkt_managers():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT m.id, m.name, m.surname, c.name AS city_name, m.phone_number, m.address, m.login, m.password
            FROM punkt_manager m
            JOIN punkt c ON m.punkt_id = c.id
        ''')

        managers = cur.fetchall()
    except Exception as e:
        # Обработка ошибки подключения к базе данных
        return jsonify({'error': 'Ошибка при подключении к базе данных'}), 500
    finally:
        cur.close()
        conn.close()

    managers_data = []
    for manager in managers:
        manager_details = {
            'id': manager['id'],
            'name': manager['name'],
            'surname': manager['surname'],
            'address':manager['address'],
            'city_name': manager['city_name'],
            'phone_number': manager['phone_number'],
            'login': manager['login'],
            'password': manager['password']
        }
        managers_data.append(manager_details)

    return jsonify(managers_data)

@app.route('/punkt_managers')
@admin_login_required
def punkt_managers():
     return render_template("punkt_managers.html")
#------------------ Полезные ресурсы----------------
@app.route('/add_resource', methods=['POST'])
@admin_login_required
def add_resource():
    try:
        resource_name = request.form['resourceName']
        resource_description = request.form['resourceDescription']
        resource_link = request.form['resourceLink']
        resource_rate = request.form['resourceRate']

        conn = get_database_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('''
                        INSERT INTO Usefull_resource (name, description, link, rate)
                         VALUES (%s, %s, %s, %s)
                        ''',
            (resource_name, resource_description, resource_link, resource_rate))

            conn.commit()
            print("Data inserted into database successfully!")
            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            print("Error inserting data into database:", str(e))
            return jsonify({'error': str(e)})
        finally:
            cur.close()
            conn.close()
    except KeyError as ke:
        return jsonify({'error': 'Missing key in form data: {}'.format(ke)})

@app.route('/add_photos', methods=['POST'])
@admin_login_required
def add_photos():
    try:
        resource_id = request.form['resourceId']
        
        # Получение ссылок на фотографии и проверка на наличие значений
        photo_links = [
            request.form['photoLink1'] if 'photoLink1' in request.form else None,
            request.form['photoLink2'] if 'photoLink2' in request.form else None,
            request.form['photoLink3'] if 'photoLink3' in request.form else None
        ]

        conn = get_database_connection()
        cur = conn.cursor()

        try:
            for photo_link in photo_links:
                if photo_link:  # Проверка, что значение не None
                    cur.execute('''
                                INSERT INTO resourcephotos (resource_id, photo_link)
                                VALUES (%s, %s)
                                ''',
                                (resource_id, photo_link))
            conn.commit()
            print("Photos inserted into database successfully!")
            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            print("Error inserting photos into database:", str(e))
            return jsonify({'error': str(e)})
        finally:
            cur.close()
            conn.close()
    except KeyError as ke:
        return jsonify({'error': 'Missing key in form data: {}'.format(ke)})


@app.route('/get_all_resources', methods=['GET'])
@admin_login_required
def get_all_resources():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('SELECT * FROM Usefull_resource')
        resources = cur.fetchall()

        resource_list = []
        for resource in resources:
            resource_dict = {
                'id': resource[0],
                'name': resource[1],
                'description': resource[2],
                'link': resource[3],
                'rate': resource[4]
            }
            resource_list.append(resource_dict)

        return jsonify(resource_list)
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        cur.close()
        conn.close()

@app.route('/get_all_resources_with_photos', methods=['GET'])
def get_all_resources_with_photos():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Выборка ресурсов с фотографиями, отсортированных по рейтингу
        cur.execute('''
                    SELECT ur.id, ur.name, ur.description, ur.link, ur.rate, array_agg(rp.photo_link) AS photo_links
                    FROM Usefull_resource ur
                    LEFT JOIN resourcephotos rp ON ur.id = rp.resource_id
                    GROUP BY ur.id, ur.name, ur.description, ur.link, ur.rate
                    ORDER BY ur.rate DESC
                    ''')
        
        resources = cur.fetchall()

        resource_list = []
        for resource in resources:
            resource_dict = {
                'id': resource[0],
                'name': resource[1],
                'description': resource[2],
                'link': resource[3],
                'rate': resource[4],
                'photo_links': ','.join(resource[5]) if resource[5] else ''  # Строка с фото, разделенными запятыми
            }
            resource_list.append(resource_dict)

        return jsonify(resource_list)
    
    except Exception as e:
        return jsonify({'error': str(e)})
    
    finally:
        cur.close()
        conn.close()

@app.route('/use_resources')
@admin_login_required
def res_page():
    return render_template('use_res.html')  

@app.route('/use_resourcesuser')
def useres_page():
    return render_template('shop.html')  

@app.route('/user_reso')
def page_res():
    return render_template("res_user.html")
#-------------Инвентаризация-----------
@app.route("/inventarization")
@admin_login_required
def inv_page():
    return render_template("inventarization.html")

@app.route('/get_orders_summary_by_status', methods=['GET'])
def get_orders_summary_by_status():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
    SELECT 
    u.id AS user_id,
    u.name || ' ' || u.surname AS client_fio,
    c.phone_num AS phone_number,
    o.comment AS comment,
    COUNT(o.id) AS total_parcel_count,
    SUM(o.massa) AS total_parcel_weight,
    SUM(o.amount) AS total_amount
FROM "Order" o
JOIN "User" u ON o.user_id = u.id
LEFT JOIN "contact" c ON u.id = c.user_id
WHERE o.order_status_id = 3 and o.city_id=1
GROUP BY u.id, client_fio, phone_number, o.comment;

''')


        orders_summary = cur.fetchall()
    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

    summary_data = []
    for summary in orders_summary:
        summary_details = {
            'user_id': summary['user_id'],
            'client_fio': summary['client_fio'],
            'phone_number': summary['phone_number'],
            'comment': summary['comment'],
            'total_parcel_count': summary['total_parcel_count'],
            'total_parcel_weight': summary['total_parcel_weight'],
            'total_amount': summary['total_amount']
        }
        summary_data.append(summary_details)

    return jsonify(summary_data)

@app.route('/save_comment', methods=['POST'])
@admin_login_required
def save_comment():
    try:
        user_id = request.json['user_id']
        comment = request.json['comment']
        
        conn = get_database_connection()
        cur = conn.cursor()

        # Обновление комментария во всех заказах клиента с указанным статусом
        cur.execute('''
            UPDATE "Order" 
            SET comment = %s
            WHERE user_id = %s AND order_status_id = 3;
        ''', (comment, user_id))

        conn.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()


#-------------USERS---------------
@app.route('/manage_users')
@admin_login_required
def manage_users():

    return render_template('manage_users.html')  

def insert_user(id, name, surname, otchestvo, date_of_birth, city_id, user_tarif, user_discount):
    conn = get_database_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO "User" (id, name, surname, otchestvo, date_of_birth, city_id, user_tarif, user_discount) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    """, (id, name, surname, otchestvo, date_of_birth, city_id, user_tarif, user_discount))
    conn.commit()
    cur.close()
    conn.close()

def insert_contact(phone_num, extra_phone_num, tg_nickname, email, user_id, tg_user_id, coment):
    conn = get_database_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contact (phone_num, extra_phone_num, tg_nickname, email, user_id, tg_user_id, coment) 
        VALUES (%s, %s, %s, %s, %s, %s, %s);
    """, (phone_num, extra_phone_num, tg_nickname, email, user_id, tg_user_id, coment))
    conn.commit()
    cur.close()
    conn.close()

@app.route('/create_user', methods=['POST'])
def create_user():
    data = request.json
    print("Received data:", data)  # Добавляем эту строку для вывода полученных данных на сервере
    name = data.get('name')
    user_id=data.get('code_cl')
    surname = data.get('surname')
    otchestvo = data.get('otchestvo')
    date_of_birth = data.get('dateOfBirth')
    city_id = data.get('city')
    user_tarif = data.get('userTarif')
    user_discount = data.get('user_discount')
    phone_num = data.get('phone_num')
    extra_phone_num = data.get('extra_phone_num')
    tg_nickname = data.get('tg_nickname')
    email = data.get('email')
    tg_user_id = data.get('tg_user_id')
    coment = data.get('coment')
    print("city", city_id)
    try:
        insert_user(user_id, name, surname, otchestvo, date_of_birth, city_id, user_tarif, user_discount)
        insert_contact(phone_num, extra_phone_num, tg_nickname, email, user_id, tg_user_id, coment)
        return jsonify({'message': 'User created successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get_all_users', methods=['GET'])
@admin_login_required
def get_all_users():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                u.id, u.name, u.surname, u.user_tarif,
                c.name AS city_name, 
                ct.phone_num, ct.extra_phone_num, ct.tg_nickname, ct.email
            FROM "User" u
            LEFT JOIN City c ON u.city_id = c.id
            LEFT JOIN Contact ct ON u.id = ct.user_id
        ''')

        users = cur.fetchall()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    users_data = []
    for user in users:
        user_details = {
            'id': user['id'],
            'name': user['name'],
            'surname': user['surname'],
            'user_tarif': user['user_tarif'],
            'city_name': user['city_name'],
            'phone_num': user['phone_num'],
            'extra_phone_num': user['extra_phone_num'],
            'tg_nickname': user['tg_nickname'],
            'email': user['email']
        }
        users_data.append(user_details)
        

    return jsonify(users_data)



@app.route('/get_user_by_id/<user_id>', methods=['GET'])
@admin_login_required
def get_user_by_id(user_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT
                u.id, u.name, u.surname,u.user_tarif,
                c.name AS city_name,
                ct.phone_num, ct.extra_phone_num, ct.tg_nickname, ct.email
            FROM "User" u
            LEFT JOIN City c ON u.city_id = c.id
            LEFT JOIN Contact ct ON u.id = ct.user_id
            WHERE u.id = %s
        ''', (user_id,))

        user = cur.fetchone()
        if not user:
            return jsonify({'error': 'Пользователь не найден'}), 404

        user_data = {
            'id': user['id'],
            'name': user['name'],
            'surname': user['surname'],
            'user_tarif':user['user_tarif'],
            'city_name': user['city_name'],
            'phone_num': user['phone_num'],
            'extra_phone_num': user['extra_phone_num'],
            'tg_nickname': user['tg_nickname'],
            'email': user['email']
        }

        return jsonify(user_data)
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/get_cities', methods=['GET'])
@admin_login_required
def get_cities():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('SELECT id, name FROM City')

        cities = cur.fetchall()
        city_data = [{'id': city[0], 'name': city[1]} for city in cities]

        return jsonify(city_data)
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/update_user', methods=['POST'])
@admin_login_required
def update_user():
    data = request.json
    user_id = data.get('id')

    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Получение текущего города пользователя
        cur.execute('SELECT city_id FROM "User" WHERE id = %s', (user_id,))
        current_city_id = cur.fetchone()[0]

        # Проверка, существует ли запись контакта для данного пользователя
        cur.execute('SELECT COUNT(*) FROM Contact WHERE user_id = %s', (user_id,))
        contact_exists = cur.fetchone()[0]

        # Если запись контакта не существует, создайте новую запись в таблице "Contact"
        if contact_exists == 0:
            cur.execute('''
                INSERT INTO Contact (user_id, phone_num, extra_phone_num, tg_nickname)
                VALUES (%s, %s, %s, %s)
            ''', (user_id, data['phone_num'], data['extra_phone_num'], data['tg_nickname']))
            conn.commit()

        # Обновление данных пользователя в таблице "User"
        cur.execute('''
            UPDATE "User" AS u
            SET name = %s, surname = %s, user_tarif = %s, city_id = %s
            FROM Contact AS c
            WHERE u.id = c.user_id AND u.id = %s
        ''', (data['name'], data['surname'], data['user_tarif'], data['city_id'], user_id))

        # Проверка, были ли данные обновлены в таблице "User"
        if cur.rowcount == 0:
            # Если ни одна строка не была обновлена, пользователь с указанным ID не найден
            return jsonify({'success': False, 'message': 'Пользователь с указанным ID не найден'}), 404

        conn.commit()

        # Обновление данных контакта пользователя в таблице "Contact"
        cur.execute('''
            UPDATE Contact
            SET phone_num = %s, extra_phone_num = %s, tg_nickname = %s
            WHERE user_id = %s
        ''', (data['phone_num'], data['extra_phone_num'], data['tg_nickname'], user_id))

        conn.commit()

        # Проверка, были ли данные обновлены в таблице "Contact"
        if cur.rowcount == 0:
            # Если ни одна строка не была обновлена, это может быть связано с отсутствием контактной информации
            return jsonify({'success': False, 'message': 'Контактные данные пользователя не найдены или не могут быть обновлены'}), 404

        # Обновление города в заказах пользователя
        cur.execute('''
            UPDATE "Order"
            SET city_id = %s
            WHERE user_id = %s AND city_id = %s
        ''', (data['city_id'], user_id, current_city_id))

        conn.commit()

        return jsonify({'success': True, 'message': 'Данные пользователя успешно обновлены'}), 200
    except Exception as e:
        conn.rollback()
        logging.error(f'Ошибка при обновлении данных пользователя: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()



#-----------PAYMENT---------------------
        
@app.route('/payment')
@login_required_for_sorting
def payment_page():

    return render_template('pay2.html')

@app.route('/payment2')
@admin_login_required
def pay2method():
    return render_template("payment.html")


@app.route('/apply_discount_to_all_orders', methods=['POST'])
@login_required_for_sorting
def apply_discount_to_all_orders():
    try:
        # Получаем данные из запроса
        data = request.json
        discount = data.get('discount')
        orders = data.get('orders')
        

        # Проверяем, что полученные данные корректны
        if discount is None or not isinstance(discount, (float, int)) or discount <= 0 or orders is None or not isinstance(orders, list):
            return jsonify({'success': False, 'error': 'Invalid discount or orders data provided'}), 400

        # Подключаемся к базе данных
        conn = get_database_connection()
        cur = conn.cursor()

        try:
            # Обновляем информацию о скидке, тарифе и сумме для каждого заказа
            for order in orders:
                track_code = order.get('trackCode')
                new_discount = order.get('newDiscount')
                new_tarif = order.get('newTarif')
                new_amount = order.get('newAmount')

                if track_code is None or new_discount is None or new_tarif is None or new_amount is None:
                    continue

                cur.execute('''
                UPDATE "Order" 
                SET discount_amount = %s, user_tarif = %s, amount = %s
                WHERE track_code = %s
                ''',
                    (new_discount, new_tarif, new_amount, track_code))
                print("track code: ", track_code)

            # Фиксируем изменения в базе данных
            conn.commit()


            return jsonify({'success': True}), 200
        except Exception as e:
            app.logger.error("Error updating discount, tarif and amount for all orders: %s", str(e))
            conn.rollback()
            return jsonify({'success': False, 'error': 'Error updating discount, tarif and amount for all orders'}), 500
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        app.logger.error("Error processing request: %s", str(e))
        return jsonify({'success': False, 'error': 'Error processing request'}), 500


@app.route('/get_order_info', methods=['POST'])
@login_required_for_sorting
def get_order_info():
    try:
        track_code = request.form.get('trackCode')

        if not track_code or not isinstance(track_code, str) or len(track_code) < 2:
            return jsonify({'error': 'Invalid track code provided'}), 400

        app.logger.info("Received track code: %s", track_code)

        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            cur.execute('''
                        SELECT o.id, u.name AS user_name, u.surname, u.otchestvo, c.name AS city_name, o.user_tarif, os.name AS order_status, 
                        o.massa, o.payment_status, o.amount, o.track_code, o.discount_amount
                        FROM "Order" o
                        JOIN "User" u ON o.user_id = u.id
                        JOIN City c ON o.city_id = c.id
                        JOIN order_status os ON o.order_status_id = os.id
                        WHERE o.track_code = %s
                        ''',
                        (track_code,))
            order_info = cur.fetchone()
            if order_info:
                return jsonify({
                    'success': True,
                    'order_info': order_info
                })
            else:
                return jsonify({'error': 'Order not found for track code: {}'.format(track_code)})
        except Exception as e:
            app.logger.error("Error executing database query: %s", str(e))
            return jsonify({'error': 'Error executing database query'}), 500
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        app.logger.error("Error processing request: %s", str(e))
        return jsonify({'error': 'Error processing request'}), 500

@app.route('/payment_types', methods=['GET'])
@login_required_for_sorting
def get_payment_types():
    try:
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, name FROM payment_type')
        payment_types = cur.fetchall()
        cur.close()
        conn.close()

        payment_types_dict = [{'id': payment_type[0], 'name': payment_type[1]} for payment_type in payment_types]
        
        return jsonify({'payment_types': payment_types_dict})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/user_orders')
@admin_login_required
def orders_user_page():
    return render_template("user_orders.html")

@app.route('/get_orders_by_user_and_status', methods=['GET'])
def get_orders_by_user_and_status():
    try:
        # Получение параметров запроса: user_id и status_id
        user_id = request.args.get('user_id')
        status_id = request.args.get('status_id')

        # Установление соединения с базой данных
        conn = get_database_connection()
        cur = conn.cursor()

        # Выполнение запроса к базе данных
        cur.execute("SELECT id, city_id, data_send_from_china, user_id, track_code, order_status_id, amount FROM \"Order\" WHERE user_id = %s AND order_status_id = %s", (user_id, status_id))


        # Получение результатов запроса
        orders = cur.fetchall()

        # Формирование списка словарей с данными о заказах
        orders_list = []
        for order in orders:
            order_dict = {
                'id': order[0],
                'city_id': order[1],
                'data_send_from_china': order[2],
                'user_id': order[3],
                'track_code': order[4],
                'order_status_id': order[5],
                'amount': order[6]
            }
            orders_list.append(order_dict)
        # Возвращение результатов в формате JSON
        return jsonify({'orders': orders_list})

    except Exception as e:
        return jsonify({'error': str(e)})

    finally:
        # Закрытие соединения с базой данных
        cur.close()
        conn.close()



@app.route('/pay_selected_orders', methods=['POST'])
@login_required_for_sorting
def pay_selected_orders():
    try:
        # Получаем данные из запроса
        data = request.json
        manager_id = data.get('manager_id')
        payment_type_name = data.get('payment_type_name')
        track_codes = data.get('track_codes')

        # Получаем текущую дату
        current_date = datetime.now().strftime('%Y-%m-%d')

        # Получаем ID типа оплаты из таблицы payment_type по его имени
        conn = get_database_connection()
        cur = conn.cursor()
        

        # Подготавливаем SQL-запрос для обновления выбранных заказов
        query = '''
        UPDATE "Order"
        SET order_status_id = 4,
        payment_type_id = %s,
        pay_date = %s,
        payment_status = TRUE,
        manager_id = %s
        WHERE order_status_id <> 4 AND track_code IN %s
        '''

        # Выполняем обновление заказов
        cur.execute(query, (payment_type_name, current_date, manager_id, tuple(track_codes)))
        conn.commit()

        # Закрываем соединение с базой данных
        cur.close()
        conn.close()

        # Возвращаем успешный результат
        return jsonify({'success': 'Выбранные посылки успешно оплачены'})
    except Exception as e:
        # В случае ошибки возвращаем сообщение об ошибке
        return jsonify({'error': str(e)})


#STATISTS
@app.route('/calculate_daily_payment', methods=['GET'])
@admin_login_required
def calculate_daily_payment():
    try:
        # Получаем текущую дату
        current_date = date.today().strftime('%Y-%m-%d')

        # Запрос для получения суммы заказов, оплаченных сегодня
        query = '''
        SELECT SUM(amount) FROM "Order"
        WHERE pay_date = %s
        '''
        
        # Выполняем запрос
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute(query, (current_date,))
        total_amount = cur.fetchone()[0]

        # Если нет оплаченных заказов сегодня, вернем 0
        if total_amount is None:
            total_amount = 0

        # Закрываем соединение с базой данных
        cur.close()
        conn.close()

        # Возвращаем сумму оплаченных заказов сегодня
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        # В случае ошибки возвращаем сообщение об ошибке
        return jsonify({'error': str(e)})

@app.route('/total_orders_today_cash', methods=['GET'])
@admin_login_required
def total_orders_today():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Получение общей суммы заказов на сегодня с типом оплаты равным 1
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 1 AND DATE(pay_date) = %s
        ''', (date.today(),))
        
        total_amount = cur.fetchone()[0] or 0  # Если сумма равна None, то заменяем на 0

        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Ошибка при получении общей суммы заказов на сегодня: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/total_orders_today_elkart', methods=['GET'])
@admin_login_required
def total_orders_today_2():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Получение общей суммы заказов на сегодня с типом оплаты равным 2
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 2 AND DATE(pay_date) = %s
        ''', (date.today(),))
        
        total_amount = cur.fetchone()[0] or 0  # Если сумма равна None, то заменяем на 0

        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Ошибка при получении общей суммы заказов на сегодня: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/total_orders_today_mbank', methods=['GET'])
@admin_login_required
def total_orders_today_3():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Получение общей суммы заказов на сегодня с типом оплаты равным 3
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 3 AND DATE(pay_date) = %s
        ''', (date.today(),))
        
        total_amount = cur.fetchone()[0] or 0  # Если сумма равна None, то заменяем на 0

        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Ошибка при получении общей суммы заказов на сегодня: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/total_orders_today_odengi', methods=['GET'])
@admin_login_required
def total_orders_today_4():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Получение общей суммы заказов на сегодня с типом оплаты равным 4
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 4 AND DATE(pay_date) = %s
        ''', (date.today(),))
        
        total_amount = cur.fetchone()[0] or 0  # Если сумма равна None, то заменяем на 0

        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Ошибка при получении общей суммы заказов на сегодня: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/get_user_orders/<int:user_id>', methods=['GET'])

def get_user_orders(user_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT o.data_send_from_china, o.track_code, os.name AS order_status, 
                   o.user_tarif, o.discount_amount,
                   o.massa, o.comment, o.sort_date, o.amount,
                   u.name || ' ' || u.surname AS client_fio, u.id AS user_id, 
                   c.name AS city_name, 
                   ct.phone_num
                   
            FROM "Order" o
            JOIN Order_status os ON o.order_status_id = os.id
            LEFT JOIN "User" u ON o.user_id = u.id
            LEFT JOIN city c ON u.city_id = c.id
            LEFT JOIN contact ct ON u.id = ct.user_id
            WHERE o.user_id = %s AND o.order_status_id = 3
        ''', (user_id,))

        orders = cur.fetchall()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    orders_data = [dict(order) for order in orders]
    return jsonify(orders_data)

@app.route('/update_orders', methods=['POST'])
@admin_login_required
def update_orders():
    user_id = request.form.get('user_id')

    try:
        conn = get_database_connection()  
        cur = conn.cursor()

        # Обновляем статус и вставляем текущую дату в поле pay_date для всех заказов пользователя
        cur.execute('''
            UPDATE "Order"
            SET order_status_id = 4, pay_date = %s
            WHERE user_id = %s AND order_status_id = 3
        ''', (datetime.datetime.now(), user_id))  

        conn.commit()
        return 'Заказы успешно обновлены'
    except Exception as e:
        logging.error(f'Ошибка при обновлении заказов: {e}')
        return jsonify({'error': 'Ошибка при обновлении заказов'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/order_status_statistics')
def order_status_statistics():
    conn = get_database_connection()
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT os.name AS status, COUNT(*) AS count
            FROM "Order" o
            JOIN Order_status os ON o.order_status_id = os.id
            GROUP BY os.name
        ''')
        rows = cur.fetchall()
        statistics = {status: count for status, count in rows}
        return jsonify(statistics)
    except psycopg2.Error as e:
        print("Error fetching order status statistics:", e)
    finally:
        cur.close()
        conn.close()


#--------------------USER-----------------------
@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        user_id = request.form['user_id']
        password = request.form['password']
        
        # Проверка учетных данных
        if check_user_credentials(user_id, password):
            session['user_id'] = user_id
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Invalid credentials. Please try again.'})

    return render_template('sign-in.html')




@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/order-count/<int:user_id>')
def get_order_count(user_id):
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute('SELECT COUNT(*) FROM "Order" WHERE user_id = %s', (user_id,))
    order_count = cursor.fetchone()[0]
    return jsonify({'order_count': order_count})

def get_order_counts_by_status(user_id):
    connection = get_database_connection() 
    cursor = connection.cursor()

    cursor.execute('''
        SELECT order_status_id, COUNT(*), SUM(amount), SUM(massa)
        FROM "Order"
        WHERE user_id = %s
        GROUP BY order_status_id
    ''', (user_id,))

    order_counts = cursor.fetchall()  # Получение результатов запроса

    order_counts_by_status = {status_id: {'count': count, 'total_amount': total_amount, 'total_massa': total_massa} 
                              for status_id, count, total_amount, total_massa in order_counts}

    cursor.close()
    connection.close()

    return order_counts_by_status



@app.route('/search-order')
def search_order():
    track_code = request.args.get('track_code')
    if not track_code:
        return jsonify({'error': 'Track code is required'}), 400

    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute('''
        SELECT o.data_send_from_china, os.name AS order_status, u.name, u.surname
        FROM "Order" o
        INNER JOIN Order_status os ON o.order_status_id = os.id
        INNER JOIN "User" u ON o.user_id = u.id
        WHERE o.track_code = %s
    ''', (track_code,))
    order_data = cursor.fetchone()
    cursor.close()
    connection.close()

    if not order_data:
        return jsonify({'error': 'Order not found'}), 404

    order_details = {
        'date_sent_from_china': order_data[0],
        'order_status': order_data[1],
        'user_name': order_data[2],
        'user_surname': order_data[3]
    }
    print(order_details)  # Добавляем вывод в консоль
    return jsonify(order_details), 200

# def check_user_credentials(user_id, password):
#     connection = get_database_connection()
#     cursor = connection.cursor()
    
#     cursor.execute('SELECT name, phone_num FROM "User" INNER JOIN Contact ON "User".id = Contact.user_id WHERE "User".id = %s', (user_id,))
#     user_data = cursor.fetchone()
    
#     if user_data:
#         name, phone_num = user_data
#         if password == phone_num:  
#             session['user_id'] = user_id
#             session['username'] = name
#             print(f"User ID {user_id} and username {name} saved in session.")
#             return True
    
#     return False


 
def get_orders_by_status_for_user(user_id):
    # Подключение к базе данных
    connection = get_database_connection()
    cursor = connection.cursor()

    # Выполнение SQL-запроса для получения заказов пользователя с группировкой по order_status_id
    cursor.execute('''
        SELECT order_status_id, ARRAY_AGG(track_code) AS track_codes, ARRAY_AGG(data_send_from_china) AS dates,
               ARRAY_AGG(amount) AS amounts, ARRAY_AGG(massa) AS masses
        FROM "Order"
        WHERE user_id = %s
        GROUP BY order_status_id
    ''', (user_id,))

    # Извлечение всех результатов из запроса
    orders_by_status = cursor.fetchall()

    # Закрытие курсора и соединения с базой данных
    cursor.close()
    connection.close()

    return orders_by_status


@app.route('/user')
def user_page():
    user_id = session.get('user_id')
    order_counts = get_order_counts_by_status(user_id)
    if user_id:
        return render_template('user_info.html', user_id=user_id, order_counts=order_counts)
    else:
        return redirect(url_for('login'))

@app.route('/use_videos')
def user_videos():
    user_id = session.get('user_id')
    try:
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Fetch city_id and punkt_id for the user
        cur.execute('SELECT city_id, punkt_id FROM "User" WHERE id = %s', (user_id,))
        result = cur.fetchone()
        if result:
            city_id, punkt_id = result
        else:
            return jsonify({'error': 'User not found'})

        # Fetch code for the punkt_id from punkt table
        cur.execute('SELECT code FROM punkt WHERE id = %s', (punkt_id,))
        code = cur.fetchone()[0]

        return render_template("user_videos.html", user_id=user_id, city_id=city_id, punkt_code=code)
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        cur.close()
        conn.close()



@app.route('/order-status/<int:status_id>')
def get_orders_by_status(status_id):
    user_id = session.get('user_id')  # Получаем идентификатор пользователя из сессии
    if user_id is None:
        return jsonify({'error': 'User not logged in'}), 401  # Возвращаем ошибку, если пользователь не вошел в систему

    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute('''
        SELECT track_code, data_send_from_china, amount, massa
        FROM "Order"
        WHERE order_status_id = %s AND user_id = %s
    ''', (status_id, user_id))
    
    orders = cursor.fetchall()

    cursor.close()
    connection.close()

    return jsonify(orders)
@app.route('/ver_shopped')
def ver_shop():
    user_id = session.get('user_id')
    if user_id:
        return render_template('tables.html')
    else:
        return redirect(url_for('login'))


@app.route('/user_stat')
def user_stat():
    user_id = session.get('user_id')
    order_counts = get_order_counts_by_status(user_id)
    total_amount = total_order_amount()
    total_weight = get_total_order_weight(user_id)
    last_month_count = get_order_count_current_month(user_id)
    last_month_order_amount = get_order_amount_current_month(user_id)  # Correct function call
    print("sum= ", last_month_order_amount)
    
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute('''
        SELECT data_send_from_china, COUNT(*)
        FROM "Order"
        WHERE user_id = %s
        GROUP BY data_send_from_china
    ''', (user_id,))
    
    order_counts_by_date = cursor.fetchall()

    cursor.execute('''
        SELECT sort_date, SUM(amount)
        FROM "Order"
        WHERE user_id = %s
        GROUP BY sort_date
    ''', (user_id,))
    
    order_counts_by_amount = cursor.fetchall()

    cursor.close()
    connection.close()

    dates = [str(row[0]) for row in order_counts_by_date]
    counts = [row[1] for row in order_counts_by_date]

    amount_dates = [str(row[0]) for row in order_counts_by_amount]
    amounts = [row[1] for row in order_counts_by_amount]

    if user_id:
        return render_template('stat.html', user_id=user_id, order_counts=order_counts, total_amount=total_amount, total_weight=total_weight, dates=dates, counts=counts, amount_dates=amount_dates, amounts=amounts, last_month_count=last_month_count, last_month_order_amount=last_month_order_amount)
    else:
        return redirect(url_for('login'))

def get_order_count_current_month(user_id):
    current_date = datetime.now().date()
    start_date = current_date.replace(day=1)  # First day of the current month

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = current_date.strftime('%Y-%m-%d')

    print(f"get_order_count_current_month - User ID: {user_id}")
    print(f"Start Date: {start_date_str}")
    print(f"End Date: {end_date_str}")

    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute('''
        SELECT COUNT(*)
        FROM "Order"
        WHERE user_id = %s
        AND pay_date >= %s
        AND pay_date <= %s
    ''', (user_id, start_date_str, end_date_str))

    order_count = cursor.fetchone()[0]
    cursor.close()
    connection.close()

    print(f"Order Count Query Result: {order_count}")

    return order_count

def get_order_amount_current_month(user_id):
    current_date = datetime.now().date()
    start_date = current_date.replace(day=1)  # First day of the current month

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = current_date.strftime('%Y-%m-%d')

    print(f"get_order_amount_current_month - User ID: {user_id}")
    print(f"Start Date: {start_date_str}")
    print(f"End Date: {end_date_str}")

    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute('''
        SELECT SUM(amount)
        FROM "Order"
        WHERE user_id = %s
        AND pay_date >= %s
        AND pay_date <= %s
    ''', (user_id, start_date_str, end_date_str))

    order_amount = cursor.fetchone()[0]

    print(f"Order Amount Query Result: {order_amount}")

    cursor.close()
    connection.close()

    return order_amount

@app.route('/total-order-amount')
def total_order_amount():
    user_id = session.get('user_id')
    print(f"User ID: {user_id}")
    
    connection = get_database_connection()
    cursor = connection.cursor()
    
    sql_query = '''
        SELECT SUM(amount)
        FROM "Order"
        WHERE user_id = %s
    '''
    

    cursor.execute(sql_query, (user_id,))
    
    total_amount = cursor.fetchone()[0] or 0  

    cursor.close()
    connection.close()

    if total_amount is not None:
        return jsonify({'total_amount': total_amount})
    else:
        return jsonify({'error': 'Failed to retrieve total order amount'}), 500

@app.route('/total-order-weight')
def total_order_weight():
    user_id = session.get('user_id')
    total_weight = get_total_order_weight(user_id)
    if total_weight is not None:
        return jsonify({'total_weight': total_weight})
    else:
        return jsonify({'error': 'Failed to retrieve total order weight'}), 500
        
def get_total_order_weight(user_id):
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute('''
        SELECT SUM(massa)
        FROM "Order"
        WHERE user_id = %s
    ''', (user_id,))

    total_order_weight = cursor.fetchone()[0] or 0  

    cursor.close()
    connection.close()

    return total_order_weight    

def get_dollar_rate():
    response = requests.get('https://www.nbkr.kg/XML/daily.xml')
    if response.status_code == 200:
        root = ET.fromstring(response.content)
        for currency in root.findall("./Currency"):
            if currency.get("ISOCode") == "USD":
                return currency.find("Value").text
    return None

def get_average_order_amount(user_id):
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute('''
        SELECT AVG(amount)
        FROM "Order"
        WHERE user_id = %s
    ''', (user_id,))

    average_order_amount = cursor.fetchone()[0] or 0  

    cursor.close()
    connection.close()

    return average_order_amount

@app.route('/average-order-amount')
def average_order_amount():
    user_id = session.get('user_id')
    average_amount = get_average_order_amount(user_id)
    if average_amount is not None:
        return jsonify({'average_amount': average_amount})
    else:
        return jsonify({'error': 'Failed to retrieve average order amount'}), 500

@app.route('/nbkr-api')
def fetch_dollar_rate():
    rate = get_dollar_rate()
    if rate:
        return jsonify({"rate": rate})  # Возвращаем JSON-объект
    else:
        return jsonify({"error": "Error fetching dollar rate"}), 500  # Отправляем ошибку с HTTP статусом 500

@app.route('/nbkr-api-yuan')
def get_yuan_rate():
    url = "https://www.nbkr.kg/XML/weekly.xml"
    response = requests.get(url)
    if response.status_code == 200:
        root = ET.fromstring(response.content)
        for currency in root.findall(".//Currency"):
            if currency.attrib.get("ISOCode") == "CNY":
                return jsonify({"rate": currency.find("Value").text})
    return jsonify({"error": "Unable to retrieve Yuan exchange rate"}), 500

# @app.route('/force_500')
# def force_500():
#     # Вызываем ошибку 500
#     abort(500)

# Роут для страницы ошибки 404 (Страница не найдена)
# @app.errorhandler(404)
# def not_found_error(error):
#     return render_template('pages-404.html'), 404

# # Роут для страницы ошибки 403 (Доступ запрещен)
# @app.errorhandler(403)
# def forbidden_error(error):
#     return render_template('page-403.html'), 403





#-----------lessons
@app.route('/lessons')
@admin_login_required
def lesson_page():
    return render_template('lessons.html')

@app.route('/lessons_user')
def lesson_page2():
    user_id = session.get('user_id')
    if user_id:
        return render_template('user_lessons.html', user_id=user_id)
    else:
        return redirect(url_for('login'))


import time

@app.route('/get_all_categories', methods=['GET'])

def get_all_categories():
    try:

        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM Lesson_category')
        categories = cur.fetchall()
        category_list = []
        for category in categories:
            category_dict = {
                'category_id': category[0],
                'category_name': category[1],
                'category_image': category[2],
                'category_description': category[3]
            }
            category_list.append(category_dict)

        return jsonify(category_list)
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        cur.close()
        conn.close()


@app.route('/create_category', methods=['POST'])
@admin_login_required
def create_category():
    category_name = request.form['categoryName']
    category_image = request.form['categoryImage']
    category_description = request.form.get('categoryDescription', '')  # Пустая строка, если значение не указано

    try:
        conn = get_database_connection()
        cur = conn.cursor()
        # Выполняем запрос к базе данных для создания категории
        cur.execute('''
            INSERT INTO lesson_category (category_name, category_image, category_description)
            VALUES (%s, %s, %s)
        ''', (category_name, category_image, category_description))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        app.logger.error("Ошибка при создании категории: %s", str(e))  # Выводим ошибку в лог
        return jsonify({'error': str(e)})
    finally:
        cur.close()
        conn.close()

@app.route('/delete_category/<int:category_id>', methods=['DELETE'])
@admin_login_required
def delete_category(category_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM lesson_category WHERE category_id = %s', (category_id,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        app.logger.error("Ошибка при удалении категории: %s", str(e))  
        return jsonify({'error': str(e)})
    finally:
        cur.close()
        conn.close()

@app.route('/delete_order', methods=['DELETE'])
@admin_login_required
def delete_order():
    data = request.json
    print(data)  # Убедимся, что данные правильно получены
    track_code = data.get('track_code')
    print(track_code)
    try:
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM "Order" WHERE track_code=%s', (track_code,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        app.logger.error("Ошибка при удалении посылки: %s", str(e))  
        return jsonify({'error': str(e)})
    finally:
        cur.close()
        conn.close()



        


@app.route('/get_all_lessons')

def get_all_lessons():
    try:
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM lesson')
        lessons = cur.fetchall()
        
        # Выводим количество строк, полученных из базы данных
        print(f"Found {len(lessons)} lessons in the database")
        
        lesson_list = []
        for lesson in lessons:
            lesson_dict = {
                'lesson_id': lesson[0],
                'lesson_name': lesson[1],
                'lesson_description': lesson[2],
                'video_url': lesson[3],
                'lesson_priority': lesson[4],
                'lesson_category_id': lesson[5]
            }
            
            lesson_list.append(lesson_dict)
        
        return jsonify(lesson_list)
    except Exception as e:
        # Выводим сообщение об ошибке, если она произошла
        print(f"Error occurred: {e}")
        return jsonify({'error': str(e)})
    finally:
        if cur is not None:
            cur.close()
        conn.close()

@app.route('/create_lesson', methods=['POST'])
@admin_login_required
def create_lesson():
    try:
        lesson_name = request.form['lessonName']
        lesson_description = request.form['lessonDescription']
        video_url = request.form['videoUrl']
        lesson_priority = request.form['lessonPriority']
        lesson_category_id = request.form['categoryId']
        
        print("Received lesson data:", lesson_name, lesson_description, video_url, lesson_priority, lesson_category_id)  # Выводим полученные данные в консоль

        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO lesson (lesson_name, lesson_decription, video_url, lesson_priority, lesson_category_id)
            VALUES (%s, %s, %s, %s, %s)
        ''', (lesson_name, lesson_description, video_url, lesson_priority, lesson_category_id))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        print("Error occurred while creating lesson:", str(e))  # Выводим ошибку в консоль
        return jsonify({'error': str(e)})
    finally:
        cur.close()
        conn.close()



# Маршрут для вставки значений в таблицу "Item_category"
@app.route('/insert_item_category', methods=['POST'])
@admin_login_required
def insert_item_category():
    # Получаем данные из запроса
    name = request.form.get('name')
    description = request.form.get('description')
    image_file = request.files.get('image_file')

    # Проверка, что файл изображения был передан
    if not image_file:
        return jsonify({'error': 'No image file provided'}), 400

    try:
        # Чтение содержимого файла изображения
        image_data = image_file.read()

        # Устанавливаем соединение с базой данных
        conn = get_database_connection()
        cur = conn.cursor()

        # Выполняем SQL-запрос для вставки данных в таблицу "Item_category"
        cur.execute("""
            INSERT INTO Item_category (name, description, image) 
            VALUES (%s, %s, %s) RETURNING id;
        """, (name, description, psycopg2.Binary(image_data)))

        # Получаем ID только что вставленной записи
        item_category_id = cur.fetchone()[0]

        # Фиксируем изменения в базе данных
        conn.commit()

        # Закрываем курсор и соединение с базой данных
        cur.close()
        conn.close()

        # Возвращаем ответ с сообщением об успешной вставке и ID новой записи
        return jsonify({'message': 'Item category inserted successfully', 'item_category_id': item_category_id}), 200
    except Exception as e:
        # В случае ошибки возвращаем ответ с сообщением об ошибке
        return jsonify({'error': str(e)}), 500

@app.route('/get_all_items')
@admin_login_required
def get_all_items():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('''
            SELECT 
                item.id, item.name, item.description, item.item_category_id, 
                item.dlina, item.glubina, item.visota, item.volume,
                item.net_weight, item.gross_weight, item.density, 
                item.packaging_cost, item.domestic_shipping_cost, item.product_cost, 
                item.unit_price, item.china_bishkek_shipping_cost, item.cargo_shipping_cost, 
                item.customs_clearance_cost, item.final_price, item.product_margin, 
                item.shipping_margin, item.exchange_rate_margin, item.total_margin, 
                item.material, item.color, item.v_nalichii, 
                item_category.name AS category_name,
                encode(itemphotos.photo, 'base64') AS photo_base64
            FROM 
                item
            JOIN 
                item_category ON item.item_category_id = item_category.id
            LEFT JOIN 
                itemphotos ON item.id = itemphotos.item_id
            WHERE 
                item.v_nalichii = TRUE AND itemphotos.photo IS NOT NULL
            GROUP BY 
                item.id, item_category.name, itemphotos.photo
        ''')

        items = cur.fetchall()
        items_list = []

        for item in items:
            item_dict = {
                'id': item[0],
                'name': item[1],
                'description': item[2],
                'category_id': item[3],
                'dlina': float(item[4]) if item[4] is not None else None,
                'glubina': float(item[5]) if item[5] is not None else None,
                'visota': float(item[6]) if item[6] is not None else None,
                'volume': float(item[7]) if item[7] is not None else None,
                'net_weight': float(item[8]),
                'gross_weight': float(item[9]),
                'density': float(item[10]) if item[10] is not None else None,
                'packaging_cost': float(item[11]) if item[11] is not None else None,
                'domestic_shipping_cost': float(item[12]) if item[12] is not None else None,
                'product_cost': float(item[13]) if item[13] is not None else None,
                'unit_price': float(item[14]),
                'china_bishkek_shipping_cost': float(item[15]) if item[15] is not None else None,
                'cargo_shipping_cost': float(item[16]) if item[16] is not None else None,
                'customs_clearance_cost': float(item[17]) if item[17] is not None else None,
                'final_price': float(item[18]) if item[18] is not None else None,
                'product_margin': float(item[19]) if item[19] is not None else None,
                'shipping_margin': float(item[20]) if item[20] is not None else None,
                'exchange_rate_margin': float(item[21]) if item[21] is not None else None,
                'total_margin': float(item[22]) if item[22] is not None else None,
                'material': item[23],
                'color': item[24],
                'v_nalichii': item[25],
                'category_name': item[26],
                'photo_base64': item[27] if item[27] else None  # Base64 encoded photo
            }
            items_list.append(item_dict)

        return jsonify(items_list)

    except Exception as e:
        return jsonify({'error': str(e)}), 500  # Return error status code 500 for internal server errors

    finally:
        cur.close()
        conn.close()

@app.route('/naklvykup')
@admin_login_required
def get_vykup():
    items=get_all_items()
    return render_template("naklvikup.html", items=items)

@app.route('/sales')
@admin_login_required
def sales_page():
    items=get_all_items()
    return render_template("sales.html", items=items)


@app.route('/get_shop_items', methods=['GET'])
def get_items_with_photos_by_category():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Параметры запроса из URL
        category_id = request.args.get('categoryId')
        min_price = request.args.get('minPrice')
        max_price = request.args.get('maxPrice')
        sort_by = request.args.get('sortBy')
        search_query = request.args.get('searchQuery')

        # Составляем SQL-запрос с учетом фильтров и сортировки
        sql = '''
            SELECT 
                ic.id AS category_id, ic.name AS category_name, ic.description AS category_description,
                i.id AS item_id, i.name AS item_name, i.description AS item_description,
                i.massa, i.dlina, i.glubina, i.shirina, i.price, i.material, i.color, i.v_nalichii,
                array_agg(encode(ip.photo, 'base64')) AS photos_base64
            FROM 
                Item i
            JOIN 
                Item_category ic ON i.item_category_id = ic.id
            LEFT JOIN 
                ItemPhotos ip ON i.id = ip.item_id
            WHERE 1=1
        '''

        # Добавляем условия фильтрации
        params = []

        if category_id:
            sql += ' AND ic.id = '+category_id
            params.append(category_id)

        if min_price:
            sql += ' AND i.price >= $2'
            params.append(min_price)

        if max_price:
            sql += ' AND i.price <= $3'
            params.append(max_price)

        if search_query:
            sql += ' AND i.name ILIKE $4'
            params.append(f"%{search_query}%")

        # Добавляем сортировку
        if sort_by == 'alphabet_asc':
            sql += ' GROUP BY ic.id, ic.name, ic.description, i.id, i.name, i.description, ' \
                   'i.massa, i.dlina, i.glubina, i.shirina, i.price, i.material, i.color, i.v_nalichii ' \
                   'ORDER BY i.name ASC'
        elif sort_by == 'alphabet_desc':
            sql += ' GROUP BY ic.id, ic.name, ic.description, i.id, i.name, i.description, ' \
                   'i.massa, i.dlina, i.glubina, i.shirina, i.price, i.material, i.color, i.v_nalichii ' \
                   'ORDER BY i.name DESC'
        elif sort_by == 'price_asc':
            sql += ' GROUP BY ic.id, ic.name, ic.description, i.id, i.name, i.description, ' \
                   'i.massa, i.dlina, i.glubina, i.shirina, i.price, i.material, i.color, i.v_nalichii ' \
                   'ORDER BY i.price ASC'
        elif sort_by == 'price_desc':
            sql += ' GROUP BY ic.id, ic.name, ic.description, i.id, i.name, i.description, ' \
                   'i.massa, i.dlina, i.glubina, i.shirina, i.price, i.material, i.color, i.v_nalichii ' \
                   'ORDER BY i.price DESC'
        else:
            sql += ' GROUP BY ic.id, ic.name, ic.description, i.id, i.name, i.description, ' \
                   'i.massa, i.dlina, i.glubina, i.shirina, i.price, i.material, i.color, i.v_nalichii ' \
                   'ORDER BY i.id ASC'  # По умолчанию сортировка по идентификатору товара
        print(sql, params)
        cur.execute(sql, params)
        
        rows = cur.fetchall()
        items_by_category = {}

        for row in rows:
            category_id = row[0]
            category_name = row[1]
            category_description = row[2]
            item_id = row[3]
            item_name = row[4]
            item_description = row[5]
            massa = row[6]
            dlina = row[7]
            glubina = row[8]
            shirina = row[9]
            price = row[10]
            material = row[11]
            color = row[12]
            v_nalichii = row[13]
            photos_base64 = row[14]

            # Преобразование фотографий в список URL в формате base64
            photos_urls = [f"data:image/jpeg;base64,{photo}" for photo in photos_base64 if photo]

            # Формирование словаря с информацией о товаре
            item_info = {
                'id': item_id,
                'name': item_name,
                'description': item_description,
                'massa': massa,
                'dlina': dlina,
                'glubina': glubina,
                'shirina': shirina,
                'price': price,
                'material': material,
                'color': color,
                'v_nalichii': v_nalichii,
                'photos_urls': photos_urls
            }

            # Добавление товара в список категории или создание новой категории, если её ещё нет
            if category_id in items_by_category:
                items_by_category[category_id]['items'].append(item_info)
            else:
                items_by_category[category_id] = {
                    'id': category_id,
                    'name': category_name,
                    'description': category_description,
                    'items': [item_info]
                }

        # Преобразование словаря категорий в список для JSON ответа
        categories_list = list(items_by_category.values())

        return jsonify(categories_list)

    except psycopg2.Error as e:
        return jsonify({'error': str(e)}), 500  # Ответ с ошибкой 500 в случае проблем с базой данных

    finally:
        cur.close()
        conn.close()


@app.route('/shop')
def get_shop():
    return render_template("shop2.html")

@app.route('/get_all_item_categories', methods=['GET'])
@admin_login_required
def get_all_item_categories():
    try:
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, name, description, image FROM item_category')
        categories = cur.fetchall()
        category_list = []
        for category in categories:
            # Конвертируем бинарные данные изображения в base64 строку
            image_base64 = base64.b64encode(category[3]).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{image_base64}"
            category_dict = {
                'id': category[0],
                'name': category[1],
                'description': category[2],
                'image_url': image_url
            }
            category_list.append(category_dict)
        return jsonify(category_list)
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        cur.close()
        conn.close()

@app.route('/delete_category', methods=['DELETE'])
@admin_login_required
def delete_item_category():
    try:
        category_id = request.json['category_id']  # Получаем идентификатор категории из тела запроса
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM item_category WHERE id = %s', (category_id,))
        conn.commit()

        # Получаем список всех категорий после удаления
        categories = cur.fetchall()

        return jsonify({'message': 'Категория удалена'})
        
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        cur.close()
        conn.close()

from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

import logging

@app.route('/insert_item', methods=['POST'])
@admin_login_required
def insert_item():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Convert item availability to boolean
        item_availability = request.form.get('itemAvailability', '').lower() == 'true'

        # Добавление данных в таблицу Item
        cur.execute("""
            INSERT INTO Item (name, description, item_category_id, dlina, glubina, volume, net_weight, gross_weight, density,
                              packaging_cost, domestic_shipping_cost, product_cost, unit_price, china_bishkek_shipping_cost, 
                              cargo_shipping_cost, customs_clearance_cost, final_price, product_margin, shipping_margin,
                              exchange_rate_margin, total_margin, material, color, v_nalichii)
            VALUES (%s, %s,  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            request.form['itemName'],
            request.form['itemDescription'],
            request.form['itemCategory'],
            request.form['itemDlina'],
            request.form['itemGlubina'],
            request.form['itemVolume'],
            request.form['itemNetWeight'],
            request.form['itemGrossWeight'],
            request.form['itemDensity'],
            request.form['itemPackagingCost'],
            request.form['itemDomesticShippingCost'],
            request.form['itemProductCost'],
            request.form['itemUnitPrice'],
            request.form['itemChinaBishkekShippingCost'],
            request.form['itemCargoShippingCost'],
            request.form['itemCustomsClearanceCost'],
            request.form['itemFinalPrice'],
            request.form['itemProductMargin'],
            request.form['itemShippingMargin'],
            request.form['itemExchangeRateMargin'],
            request.form['itemTotalMargin'],
            request.form['itemMaterial'],
            request.form['itemColor'],
            item_availability
        ))
        
        # Получение id добавленного товара
        item_id = cur.fetchone()[0]

        # Добавление данных в таблицу ItemPhotos
        for i in range(1, 4):
            photo_key = f'photoLink{i}'
            if photo_key in request.files:
                photo_file = request.files[photo_key]
                if photo_file and allowed_file(photo_file.filename):
                    photo_data = photo_file.read()
                    cur.execute("""
                        INSERT INTO itemphotos (item_id, photo)
                        VALUES (%s, %s);
                    """, (item_id, photo_data))

        conn.commit()
        return jsonify({'message': 'Товар успешно добавлен', 'item_id': item_id})

    except Exception as e:
        logging.error('Произошла ошибка при добавлении товара: %s', str(e))
        logging.error('Запрос, вызвавший ошибку: %s', cur.query)  # Выводим запрос, вызвавший ошибку
        conn.rollback()  # Откатываем транзакцию в случае ошибки
        return jsonify({'error': 'Произошла внутренняя ошибка сервера. Пожалуйста, попробуйте снова позже.'}), 500

    finally:
        cur.close()
        conn.close()

@app.route('/des_items')
@admin_login_required
def item_page():
    return render_template("des_items.html")

def plogin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'punkt_manager_id' not in session:
            return redirect(url_for('punkt_manager_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/expenses')
@plogin_required
def expenses_page():
    return render_template("expenses.html")

@app.route('/add_expense', methods=['POST'])
@plogin_required
def add_expense():
    try:
        # Получаем данные из запроса
        data = request.json
        amount = data.get('amount')
        date = data.get('date')
        comment = data.get('comment')
        cost_item_id = data.get('cost_item_id')
        payment_type_id = data.get('payment_type_id')  # Получаем payment_type_id из запроса
        punkt_manager_id = session.get('punkt_manager_id')  # Получаем punkt_manager_id из сессии

        print("punkt_manager_id: ", punkt_manager_id)

        if not punkt_manager_id:
            raise ValueError('Необходимо выполнить вход.')

        # Выполняем SQL-запрос для получения punkt_id
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('SELECT punkt_id FROM punkt_manager WHERE id = %s', (punkt_manager_id,))
        result = cur.fetchone()
        if not result:
            raise ValueError('Пункт не найден для данного менеджера.')
        punkt_id = result[0]

        print("punkt_id: ", punkt_id)

        # Проверяем, что все данные присутствуют
        if not all([amount, date, cost_item_id, payment_type_id]):
            raise ValueError('Необходимо предоставить сумму, дату расхода, статью расходов и тип платежа.')

        # Выполняем SQL-запрос для добавления расхода в базу данных
        cur.execute('''
            INSERT INTO Expenses (amount, expense_date, comment, cost_item_id, payment_type_id, punkt_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (amount, date, comment, cost_item_id, payment_type_id, punkt_id))
        conn.commit()

        # Закрываем соединение с базой данных
        cur.close()
        conn.close()

        # Выводим сообщение об успешном добавлении в терминал
        print('Расход успешно добавлен:', amount, date, comment, cost_item_id, payment_type_id, punkt_id)

        # Возвращаем успешный результат
        return jsonify({'success': True, 'message': 'Расход успешно добавлен.'}), 200
    except ValueError as ve:
        # Выводим сообщение об ошибке валидации в терминал
        print('Ошибка валидации:', ve)

        # Возвращаем сообщение об ошибке валидации
        return jsonify({'error': str(ve), 'message': 'Проверьте введенные данные.'}), 400
    except Exception as e:
        # Выводим сообщение об ошибке в терминал
        print('Ошибка при добавлении расхода:', e)

        # Возвращаем сообщение об ошибке сервера
        return jsonify({'error': str(e), 'message': 'Произошла ошибка при добавлении расхода. Обратитесь к администратору.'}), 500

@app.route('/get_all_cost_items')
@plogin_required
def get_all_cost_items():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('SELECT id, name, description FROM cost_item')
        cost_items = cur.fetchall()

        # Закрываем соединение с базой данных
        cur.close()
        conn.close()

        # Преобразуем результат в список словарей для JSON
        cost_items_list = [{'id': item[0], 'name': item[1], 'description': item[2]} for item in cost_items]

        return jsonify(cost_items_list)
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/delete_cost_item/<int:cost_item_id>', methods=['DELETE'])
def delete_cost_item(cost_item_id):
    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute('''
            DELETE FROM cost_item
            WHERE id = %s
        ''', (cost_item_id,))
        
        connection.commit()
        
        if cursor.rowcount > 0:
            response = {'success': True}
        else:
            response = {'success': False, 'error': 'Статья расходов не найдена'}

    except Exception as e:
        connection.rollback()
        response = {'success': False, 'error': str(e)}
    
    finally:
        cursor.close()
        connection.close()
    
    return jsonify(response)

@app.route('/add_cost_item', methods=['POST'])
@plogin_required
def add_cost_item():
    try:
        # Получаем данные формы из запроса
        name = request.form.get('name')
        description = request.form.get('description')

        # Проверяем, чтобы имя статьи расхода было заполнено
        if not name:
            return jsonify({'error': 'Имя статьи расхода не указано'}), 400

        # Добавляем статью расхода в базу данных
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO cost_item (name, description) VALUES (%s, %s)", (name, description))
        conn.commit()
        conn.close()

        # Возвращаем успешный ответ
        return jsonify({'message': 'Статья расхода успешно добавлена'}), 200
    except Exception as e:
        # В случае ошибки возвращаем сообщение об ошибке
        return jsonify({'error': str(e)}), 500


@app.route('/delete_expense/<int:expense_id>', methods=['DELETE'])
@plogin_required
def delete_expense(expense_id):
    try:
        # Выполняем SQL-запрос для удаления расхода из базы данных по его ID
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM Expenses WHERE id = %s', (expense_id,))
        conn.commit()
        
        # Закрываем соединение с базой данных
        cur.close()
        conn.close()

        # Возвращаем успешный результат
        return jsonify({'success': True}), 200
    except Exception as e:
        # В случае ошибки возвращаем сообщение об ошибке
        return jsonify({'error': str(e)}), 500


@app.route('/expenses', methods=['GET'])
@plogin_required
def get_expenses():
    try:
        # Получаем начальную и конечную дату из параметров запроса
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        punkt_manager_id = session.get('punkt_manager_id')
        if not punkt_manager_id:
            raise ValueError('Необходимо выполнить вход.')

        # Получаем punkt_id для текущего менеджера
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute('SELECT punkt_id FROM punkt_manager WHERE id = %s', (punkt_manager_id,))
        result = cur.fetchone()
        if not result:
            raise ValueError('Пункт не найден для данного менеджера.')
        punkt_id = result['punkt_id']

        # Выполняем SQL-запрос для получения всех расходов за выбранный период и для данного пункта
        cur.execute('''
            SELECT e.id, e.amount, e.expense_date, e.comment, c.name AS cost_item_name, pt.name AS payment_type_name
            FROM Expenses e
            LEFT JOIN cost_item c ON e.cost_item_id = c.id
            LEFT JOIN payment_type pt ON e.payment_type_id = pt.id
            WHERE e.expense_date BETWEEN %s AND %s AND e.punkt_id = %s
            GROUP BY e.id, c.name, pt.name
        ''', (start_date, end_date, punkt_id))
        
        # Получаем результаты запроса
        expenses = cur.fetchall()
        
        # Закрываем соединение с базой данных
        cur.close()
        conn.close()

        # Возвращаем расходы в формате JSON
        return jsonify(expenses), 200
    except Exception as e:
        # В случае ошибки возвращаем сообщение об ошибке
        return jsonify({'error': str(e)}), 500
#----------INCOMES---------------
@app.route('/income')
@plogin_required
def income_page():
    return render_template('income.html')


@app.route('/get_all_income_items')
@plogin_required
def get_all_income_items():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('SELECT id, name, description FROM income_item')
        income_items = cur.fetchall()

        # Закрываем соединение с базой данных
        cur.close()
        conn.close()

        # Преобразуем результат в список словарей для JSON
        cost_income_list = [{'id': item[0], 'name': item[1], 'description': item[2]} for item in income_items]

        return jsonify(cost_income_list)
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/delete_income_item/<int:income_item_id>', methods=['DELETE'])
def delete_income_item(income_item_id):
    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute('''
            DELETE FROM income_item
            WHERE id = %s
        ''', (income_item_id,))
        
        connection.commit()
        
        if cursor.rowcount > 0:
            response = {'success': True}
        else:
            response = {'success': False, 'error': 'Статья прихода не найдена'}

    except Exception as e:
        connection.rollback()
        response = {'success': False, 'error': str(e)}
    
    finally:
        cursor.close()
        connection.close()
    
    return jsonify(response)

@app.route('/delete_income/<int:income_id>', methods=['DELETE'])
@plogin_required
def delete_income(income_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Выполните SQL-запрос для удаления прихода с указанным ID
        cur.execute('DELETE FROM income WHERE id = %s', (income_id,))
        conn.commit()

        # Закрываем соединение с базой данных
        cur.close()
        conn.close()

        return jsonify({'message': 'Приход успешно удален'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/add_income_item', methods=['POST'])
@plogin_required
def add_income_item():
    try:
        # Получаем данные формы из запроса
        name = request.form.get('name')
        description = request.form.get('description')

        # Проверяем, чтобы имя статьи расхода было заполнено
        if not name:
            return jsonify({'error': 'Имя статьи дохода не указано'}), 400

        # Добавляем статью расхода в базу данных
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO income_item (name, description) VALUES (%s, %s)", (name, description))
        conn.commit()
        conn.close()

        # Возвращаем успешный ответ
        return jsonify({'message': 'Статья дозхода успешно добавлена'}), 200
    except Exception as e:
        # В случае ошибки возвращаем сообщение об ошибке
        return jsonify({'error': str(e)}), 500


@app.route('/add_income', methods=['POST'])
@plogin_required  # Предполагается, что для добавления прихода также требуется авторизация пункт-менеджера
def add_income():
    try:
        # Получаем данные о приходе из запроса
        data = request.json
        name = data['name']
        amount = data['amount']
        date = data['date']
        comment = data.get('comment', '')
        income_item_id = data['income_item_id']
        
        # Получаем punkt_manager_id из сессии
        punkt_manager_id = session.get('punkt_manager_id')
        if not punkt_manager_id:
            raise ValueError('Необходимо выполнить вход.')

        # Выполняем SQL-запрос для получения punkt_id
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('SELECT punkt_id FROM punkt_manager WHERE id = %s', (punkt_manager_id,))
        result = cur.fetchone()
        if not result:
            raise ValueError('Пункт не найден для данного менеджера.')
        punkt_id = result[0]

        # Выполняем SQL-запрос для вставки нового прихода с указанием пункта
        cur.execute('''
            INSERT INTO income (name, amount, date, comment, income_item_id, punkt_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (name, amount, date, comment, income_item_id, punkt_id))
        
        # Подтверждаем транзакцию
        conn.commit()

        # Закрываем соединение с базой данных
        cur.close()
        conn.close()

        return jsonify({'message': 'Приход успешно добавлен'}), 200
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_all_incomes')
@plogin_required
def get_all_incomes():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('SELECT income.id, income.name, income.amount, income.date, income.comment, income_item.name AS income_item_name FROM income INNER JOIN income_item ON income.income_item_id = income_item.id')
        incomes = cur.fetchall()

        # Закрываем соединение с базой данных
        cur.close()
        conn.close()

        # Преобразуем результат в список словарей для JSON
        incomes_list = [{'id': item[0], 'name': item[1], 'amount': item[2], 'date': item[3].strftime('%Y-%m-%d'), 'comment': item[4], 'income_item_name': item[5]} for item in incomes]

        return jsonify(incomes_list)
    except Exception as e:
        return jsonify({'error': str(e)})


#------------КАССА по МЕНЕДЖЕРАМ---------------------------------------

@app.route('/cassa')
@plogin_required
def cassa_page():
    return render_template('cassa.html')

@app.route('/calculate_profit', methods=['GET'])
@plogin_required
def calculate_profit():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Получаем punkt_id из сессии
        punkt_manager_id = session.get('punkt_manager_id')
        if not punkt_manager_id:
            raise ValueError('Необходимо выполнить вход.')

        # Вычисляем сумму всех заказов для данного пункта
        cur.execute('''
            SELECT SUM(amount)
            FROM "Order" o
            JOIN "User" u ON o.user_id = u.id
            WHERE o.order_status_id = 4 AND u.punkt_id = (
                SELECT punkt_id FROM punkt_manager WHERE id = %s
            )
        ''', (punkt_manager_id,))
        total_orders_amount = cur.fetchone()[0] or 0

        # Вычисляем сумму всех расходов для данного пункта
        cur.execute('''
            SELECT SUM(amount)
            FROM Expenses e
            JOIN punkt_manager pm ON e.punkt_id = pm.punkt_id
            WHERE pm.id = %s
        ''', (punkt_manager_id,))
        total_expenses_amount = cur.fetchone()[0] or 0
        
        # Вычисляем сумму всех приходов для данного пункта
        cur.execute('''
            SELECT SUM(amount)
            FROM income i
            JOIN punkt_manager pm ON i.punkt_id = pm.punkt_id
            WHERE pm.id = %s
        ''', (punkt_manager_id,))
        total_income_amount = cur.fetchone()[0] or 0

        # Вычисляем прибыль для данного пункта
        profit = total_orders_amount - total_expenses_amount + total_income_amount

        return jsonify({
            'total_orders_amount': total_orders_amount,
            'total_expenses_amount': total_expenses_amount,
            'total_income_amount': total_income_amount,
            'profit': profit
        }), 200
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

from collections import defaultdict

from collections import defaultdict

import traceback

@app.route('/calculate_profit_by_date', methods=['GET'])
@plogin_required
def calculate_profit_by_date():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Получаем punkt_id из сессии
        punkt_manager_id = session.get('punkt_manager_id')
        if not punkt_manager_id:
            raise ValueError('Необходимо выполнить вход.')

        # Получаем уникальные даты оплаты заказов для данного пункта
        cur.execute('''
            SELECT DISTINCT o.pay_date
            FROM "Order" o
            JOIN "User" u ON o.user_id = u.id
            WHERE o.order_status_id = 4 AND u.punkt_id = (
                SELECT punkt_id FROM punkt_manager WHERE id = %s
            )
        ''', (punkt_manager_id,))
        order_dates = [row[0] for row in cur.fetchall()]

        # Получаем уникальные даты расходов и статьи расходов для данного пункта
        cur.execute('''
    SELECT DISTINCT e.expense_date, c.name
    FROM Expenses e
    JOIN cost_item c ON e.cost_item_id = c.id
    JOIN punkt_manager pm ON e.punkt_id = pm.punkt_id
    WHERE pm.id = %s
''', (punkt_manager_id,))

        expense_data = cur.fetchall()
        expense_dates = [row[0] for row in expense_data]
        expense_items_by_date = defaultdict(list)
        for date, item in expense_data:
            expense_items_by_date[date].append(item)

        # Получаем уникальные даты приходов для данного пункта
        cur.execute('''
            SELECT DISTINCT i.date
            FROM income i
            JOIN punkt_manager pm ON i.punkt_id = pm.punkt_id
            WHERE pm.id = %s
        ''', (punkt_manager_id,))
        income_dates = [row[0] for row in cur.fetchall()]

        # Объединяем уникальные даты заказов, расходов, приходов для данного пункта
        all_dates = set(order_dates + expense_dates + income_dates)

        # Создаем словарь для хранения прибыли, сумм заказов, расходов, приходов и статей расходов по каждой дате
        profit_by_date = defaultdict(lambda: {'total_orders_amount': 0, 'total_expenses_amount': 0, 'total_income_amount': 0, 'total_discount_amount': 0, 'profit': 0, 'expense_items': []})

        # Вычисляем сумму заказов, расходов, приходов и скидок для каждой даты
        for date in all_dates:
            # Вычисляем сумму заказов для текущей даты и данного пункта
            cur.execute('''
                SELECT SUM(o.amount)
                FROM "Order" o
                JOIN "User" u ON o.user_id = u.id
                WHERE o.pay_date = %s AND o.order_status_id = 4 AND u.punkt_id = (
                    SELECT punkt_id FROM punkt_manager WHERE id = %s
                )
            ''', (date, punkt_manager_id))
            orders_amount = cur.fetchone()[0] or 0

            # Вычисляем сумму расходов для текущей даты и данного пункта
            cur.execute('''
                SELECT SUM(e.amount)
                FROM Expenses e
                JOIN punkt_manager pm ON e.punkt_id = pm.punkt_id
                WHERE e.expense_date = %s AND pm.id = %s
            ''', (date, punkt_manager_id))
            expenses_amount = cur.fetchone()[0] or 0
            
            # Вычисляем сумму приходов для текущей даты и данного пункта
            cur.execute('''
                SELECT SUM(i.amount)
                FROM income i
                JOIN punkt_manager pm ON i.punkt_id = pm.punkt_id
                WHERE i.date = %s AND pm.id = %s
            ''', (date, punkt_manager_id))
            income_amount = cur.fetchone()[0] or 0

            # Вычисляем сумму скидок для текущей даты и данного пункта (если необходимо)
            cur.execute('''
                SELECT SUM(o.discount_amount)
                FROM "Order" o
                JOIN "User" u ON o.user_id = u.id
                WHERE o.pay_date = %s AND o.order_status_id = 4 AND u.punkt_id = (
                    SELECT punkt_id FROM punkt_manager WHERE id = %s
                )
            ''', (date, punkt_manager_id))
            discount_amount = cur.fetchone()[0] or 0

            # Получаем список статей расходов для текущей даты и данного пункта
            expense_items = expense_items_by_date.get(date, [])

            # Сохраняем данные в словаре
            profit_by_date[str(date)] = {
                'total_orders_amount': orders_amount,
                'total_expenses_amount': expenses_amount,
                'total_income_amount': income_amount,
                'total_discount_amount': discount_amount,
                'profit': orders_amount + income_amount - expenses_amount - discount_amount,
                'expense_items': expense_items
            }

        return jsonify(profit_by_date), 200
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        traceback.print_exc()  # Вывод traceback в консоль или логи сервера
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/calculate_profit_by_date_range', methods=['GET', 'POST'])
@plogin_required
def calculate_profit_by_date_range():
    try:
        if request.method == 'POST':
            data = request.json
            start_date = data.get('start_date')
            end_date = data.get('end_date')

            conn = get_database_connection()
            cur = conn.cursor()

            # Получаем punkt_id из сессии
            punkt_manager_id = session.get('punkt_manager_id')
            if not punkt_manager_id:
                raise ValueError('Необходимо выполнить вход.')

            # Получаем уникальные даты оплаты заказов в заданном диапазоне для данного пункта
            cur.execute('''
                SELECT DISTINCT o.pay_date
                FROM "Order" o
                JOIN "User" u ON o.user_id = u.id
                WHERE o.pay_date BETWEEN %s AND %s
                    AND o.order_status_id = 4
                    AND u.punkt_id = (
                        SELECT punkt_id FROM punkt_manager WHERE id = %s
                    )
            ''', (start_date, end_date, punkt_manager_id))
            order_dates = [row[0] for row in cur.fetchall()]

            # Получаем уникальные даты расходов и статьи расходов в заданном диапазоне для данного пункта
            cur.execute('''
                SELECT DISTINCT e.expense_date, c.name
                FROM Expenses e
                JOIN cost_item c ON e.cost_item_id = c.id
                JOIN punkt_manager pm ON e.punkt_id = pm.punkt_id
                WHERE e.expense_date BETWEEN %s AND %s
                    AND pm.id = %s
            ''', (start_date, end_date, punkt_manager_id))
            expense_data = cur.fetchall()
            expense_dates = [row[0] for row in expense_data]
            expense_items_by_date = defaultdict(list)
            for date, item in expense_data:
                expense_items_by_date[date].append(item)

            # Получаем уникальные даты приходов в заданном диапазоне для данного пункта
            cur.execute('''
                SELECT DISTINCT i.date
                FROM income i
                JOIN punkt_manager pm ON i.punkt_id = pm.punkt_id
                WHERE i.date BETWEEN %s AND %s
                    AND pm.id = %s
            ''', (start_date, end_date, punkt_manager_id))
            income_dates = [row[0] for row in cur.fetchall()]

            # Объединяем уникальные даты заказов, расходов, приходов для данного пункта
            all_dates = set(order_dates + expense_dates + income_dates)

            # Создаем словарь для хранения прибыли, сумм заказов, расходов, приходов и статей расходов по каждой дате
            profit_by_date = defaultdict(lambda: {'total_orders_amount': 0, 'total_expenses_amount': 0, 'total_income_amount': 0, 'total_discount_amount': 0, 'profit': 0, 'expense_items': []})

            # Вычисляем сумму заказов, расходов, приходов и скидок для каждой даты в заданном диапазоне
            for date in all_dates:
                # Вычисляем сумму заказов для текущей даты и данного пункта
                cur.execute('''
                    SELECT SUM(o.amount)
                    FROM "Order" o
                    JOIN "User" u ON o.user_id = u.id
                    WHERE o.pay_date = %s AND o.order_status_id = 4 AND u.punkt_id = (
                        SELECT punkt_id FROM punkt_manager WHERE id = %s
                    )
                ''', (date, punkt_manager_id))
                orders_amount = cur.fetchone()[0] or 0

                # Вычисляем сумму расходов для текущей даты и данного пункта
                cur.execute('''
                    SELECT SUM(e.amount)
                    FROM Expenses e
                    JOIN punkt_manager pm ON e.punkt_id = pm.punkt_id
                    WHERE e.expense_date = %s AND pm.id = %s
                ''', (date, punkt_manager_id))
                expenses_amount = cur.fetchone()[0] or 0
                
                # Вычисляем сумму приходов для текущей даты и данного пункта
                cur.execute('''
                    SELECT SUM(i.amount)
                    FROM income i
                    JOIN punkt_manager pm ON i.punkt_id = pm.punkt_id
                    WHERE i.date = %s AND pm.id = %s
                ''', (date, punkt_manager_id))
                income_amount = cur.fetchone()[0] or 0

                # Вычисляем сумму скидок для текущей даты и данного пункта (если необходимо)
                cur.execute('''
                    SELECT SUM(o.discount_amount)
                    FROM "Order" o
                    JOIN "User" u ON o.user_id = u.id
                    WHERE o.pay_date = %s AND o.order_status_id = 4 AND u.punkt_id = (
                        SELECT punkt_id FROM punkt_manager WHERE id = %s
                    )
                ''', (date, punkt_manager_id))
                discount_amount = cur.fetchone()[0] or 0

                # Получаем список статей расходов для текущей даты и данного пункта
                expense_items = expense_items_by_date.get(date, [])

                # Сохраняем данные в словаре
                profit_by_date[str(date)] = {
                    'total_orders_amount': orders_amount,
                    'total_expenses_amount': expenses_amount,
                    'total_income_amount': income_amount,
                    'total_discount_amount': discount_amount,
                    'profit': orders_amount + income_amount - expenses_amount - discount_amount,
                    'expense_items': expense_items
                }

            return jsonify(profit_by_date), 200
        else:
            return jsonify({'error': 'Метод не разрешен'}), 405
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        traceback.print_exc()  # Вывод traceback в консоль или логи сервера
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

#--------КАССА АДМИН---------------------------------------

@app.route('/cassa/admin')
def cassa_admin_page():
    return render_template('cassa_admin.html')

@app.route('/calculate_profit_admin', methods=['GET'])
@admin_login_required  # Предполагается, что у вас есть декоратор admin_required для администраторских прав
def calculate_profit_admin():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Вычисляем сумму всех заказов
        cur.execute('''
            SELECT SUM(amount)
            FROM "Order"
            WHERE order_status_id = 4
        ''')
        total_orders_amount = cur.fetchone()[0] or 0

        # Вычисляем сумму всех расходов
        cur.execute('''
            SELECT SUM(amount)
            FROM Expenses
        ''')
        total_expenses_amount = cur.fetchone()[0] or 0
        
        # Вычисляем сумму всех приходов
        cur.execute('''
            SELECT SUM(amount)
            FROM income
        ''')
        total_income_amount = cur.fetchone()[0] or 0

        # Вычисляем общую прибыль
        profit = total_orders_amount - total_expenses_amount + total_income_amount

        return jsonify({
            'total_orders_amount': total_orders_amount,
            'total_expenses_amount': total_expenses_amount,
            'total_income_amount': total_income_amount,
            'profit': profit
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/calculate_profit_by_date_admin', methods=['GET'])
@admin_login_required
def calculate_profit_by_date_admin():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Get all punkt managers with their corresponding punkt info
        cur.execute('''
            SELECT pm.id, pm.punkt_id, p.name AS punkt_name
            FROM punkt_manager pm
            JOIN punkt p ON pm.punkt_id = p.id
        ''')
        punkt_managers = cur.fetchall()

        # Initialize a dictionary to store profit data
        all_profit_data = {}

        # Iterate over each punkt manager to calculate profit data
        for pm_id, punkt_id, punkt_name in punkt_managers:
            # Get unique dates for orders
            cur.execute('''
                SELECT DISTINCT o.pay_date
                FROM "Order" o
                JOIN "User" u ON o.user_id = u.id
                WHERE o.order_status_id = 4 AND u.punkt_id = %s
            ''', (punkt_id,))
            order_dates = [row[0] for row in cur.fetchall()]

            # Get unique dates for expenses
            cur.execute('''
                SELECT DISTINCT e.expense_date
                FROM Expenses e
                JOIN punkt_manager pm ON e.punkt_id = pm.punkt_id
                WHERE pm.id = %s
            ''', (pm_id,))
            expense_dates = [row[0] for row in cur.fetchall()]

            # Get unique dates for income
            cur.execute('''
                SELECT DISTINCT i.date
                FROM income i
                JOIN punkt_manager pm ON i.punkt_id = pm.punkt_id
                WHERE pm.id = %s
            ''', (pm_id,))
            income_dates = [row[0] for row in cur.fetchall()]

            # Combine all unique dates
            all_dates = set(order_dates + expense_dates + income_dates)

            # Initialize profit data for this punkt manager
            profit_by_date = defaultdict(lambda: {'total_orders_amount': 0, 'total_expenses_amount': 0, 'total_income_amount': 0, 'total_discount_amount': 0, 'profit': 0, 'expense_items': [], 'punkt_name': punkt_name})

            # Calculate profit for each date
            for date in all_dates:
                # Calculate total orders amount for this date and punkt manager
                cur.execute('''
                    SELECT SUM(o.amount)
                    FROM "Order" o
                    JOIN "User" u ON o.user_id = u.id
                    WHERE o.pay_date = %s AND o.order_status_id = 4 AND u.punkt_id = %s
                ''', (date, punkt_id))
                orders_amount = cur.fetchone()[0] or 0

                # Calculate total expenses amount for this date and punkt manager
                cur.execute('''
                    SELECT SUM(e.amount)
                    FROM Expenses e
                    JOIN punkt_manager pm ON e.punkt_id = pm.punkt_id
                    WHERE e.expense_date = %s AND pm.id = %s
                ''', (date, pm_id))
                expenses_amount = cur.fetchone()[0] or 0

                # Calculate total income amount for this date and punkt manager
                cur.execute('''
                    SELECT SUM(i.amount)
                    FROM income i
                    JOIN punkt_manager pm ON i.punkt_id = pm.punkt_id
                    WHERE i.date = %s AND pm.id = %s
                ''', (date, pm_id))
                income_amount = cur.fetchone()[0] or 0

                # Calculate total discount amount for this date and punkt manager
                cur.execute('''
                    SELECT SUM(o.discount_amount)
                    FROM "Order" o
                    JOIN "User" u ON o.user_id = u.id
                    WHERE o.pay_date = %s AND o.order_status_id = 4 AND u.punkt_id = %s
                ''', (date, punkt_id))
                discount_amount = cur.fetchone()[0] or 0

                # Get expense items for this date and punkt manager
                cur.execute('''
                    SELECT c.name
                    FROM Expenses e
                    JOIN cost_item c ON e.cost_item_id = c.id
                    WHERE e.expense_date = %s AND e.punkt_id = %s
                ''', (date, punkt_id))
                expense_items = [row[0] for row in cur.fetchall()]

                # Save data to profit_by_date dictionary
                profit_by_date[str(date)] = {
                    'total_orders_amount': orders_amount,
                    'total_expenses_amount': expenses_amount,
                    'total_income_amount': income_amount,
                    'total_discount_amount': discount_amount,
                    'profit': orders_amount + income_amount - expenses_amount - discount_amount,
                    'expense_items': expense_items,
                    'punkt_name': punkt_name
                }

            # Store profit data for this punkt manager
            all_profit_data[pm_id] = profit_by_date

        return jsonify(all_profit_data), 200

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        traceback.print_exc()  # Output traceback to console or server logs
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/calculate_profit_by_date_range_admin', methods=['GET', 'POST'])
@admin_login_required
def calculate_profit_by_date_range_admin():
    try:
        if request.method == 'POST':
            data = request.json
            start_date = data.get('start_date')
            end_date = data.get('end_date')

            conn = get_database_connection()
            cur = conn.cursor()

            # Get all point managers with their corresponding point info
            cur.execute('''
                SELECT pm.id, pm.punkt_id, p.name AS punkt_name
                FROM punkt_manager pm
                JOIN punkt p ON pm.punkt_id = p.id
            ''')
            punkt_managers = cur.fetchall()

            # Initialize a dictionary to store profit data
            all_profit_data = {}

            # Iterate over each point manager to calculate profit data
            for pm_id, punkt_id, punkt_name in punkt_managers:
                # Get unique dates for orders within the specified range
                cur.execute('''
                    SELECT DISTINCT o.pay_date
                    FROM "Order" o
                    JOIN "User" u ON o.user_id = u.id
                    WHERE o.pay_date BETWEEN %s AND %s
                        AND o.order_status_id = 4
                        AND u.punkt_id = %s
                ''', (start_date, end_date, punkt_id))
                order_dates = [row[0] for row in cur.fetchall()]

                # Get unique dates for expenses within the specified range
                cur.execute('''
                    SELECT DISTINCT e.expense_date
                    FROM Expenses e
                    JOIN punkt_manager pm ON e.punkt_id = pm.punkt_id
                    WHERE e.expense_date BETWEEN %s AND %s
                        AND pm.id = %s
                ''', (start_date, end_date, pm_id))
                expense_dates = [row[0] for row in cur.fetchall()]

                # Get unique dates for income within the specified range
                cur.execute('''
                    SELECT DISTINCT i.date
                    FROM income i
                    JOIN punkt_manager pm ON i.punkt_id = pm.punkt_id
                    WHERE i.date BETWEEN %s AND %s
                        AND pm.id = %s
                ''', (start_date, end_date, pm_id))
                income_dates = [row[0] for row in cur.fetchall()]

                # Combine all unique dates
                all_dates = set(order_dates + expense_dates + income_dates)

                # Initialize profit data for this point manager
                profit_by_date = defaultdict(lambda: {'total_orders_amount': 0, 'total_expenses_amount': 0, 'total_income_amount': 0, 'total_discount_amount': 0, 'profit': 0, 'expense_items': [], 'punkt_name': punkt_name})

                # Calculate profit for each date
                for date in all_dates:
                    # Calculate total orders amount for this date and point manager
                    cur.execute('''
                        SELECT SUM(o.amount)
                        FROM "Order" o
                        JOIN "User" u ON o.user_id = u.id
                        WHERE o.pay_date = %s AND o.order_status_id = 4 AND u.punkt_id = %s
                    ''', (date, punkt_id))
                    orders_amount = cur.fetchone()[0] or 0

                    # Calculate total expenses amount for this date and point manager
                    cur.execute('''
                        SELECT SUM(e.amount)
                        FROM Expenses e
                        JOIN punkt_manager pm ON e.punkt_id = pm.punkt_id
                        WHERE e.expense_date = %s AND pm.id = %s
                    ''', (date, pm_id))
                    expenses_amount = cur.fetchone()[0] or 0

                    # Calculate total income amount for this date and point manager
                    cur.execute('''
                        SELECT SUM(i.amount)
                        FROM income i
                        JOIN punkt_manager pm ON i.punkt_id = pm.punkt_id
                        WHERE i.date = %s AND pm.id = %s
                    ''', (date, pm_id))
                    income_amount = cur.fetchone()[0] or 0

                    # Calculate total discount amount for this date and point manager
                    cur.execute('''
                        SELECT SUM(o.discount_amount)
                        FROM "Order" o
                        JOIN "User" u ON o.user_id = u.id
                        WHERE o.pay_date = %s AND o.order_status_id = 4 AND u.punkt_id = %s
                    ''', (date, punkt_id))
                    discount_amount = cur.fetchone()[0] or 0

                    # Get expense items for this date and point manager
                    cur.execute('''
                        SELECT c.name
                        FROM Expenses e
                        JOIN cost_item c ON e.cost_item_id = c.id
                        WHERE e.expense_date = %s AND e.punkt_id = %s
                    ''', (date, punkt_id))
                    expense_items = [row[0] for row in cur.fetchall()]

                    # Save data to profit_by_date dictionary
                    profit_by_date[str(date)] = {
                        'total_orders_amount': orders_amount,
                        'total_expenses_amount': expenses_amount,
                        'total_income_amount': income_amount,
                        'total_discount_amount': discount_amount,
                        'profit': orders_amount + income_amount - expenses_amount - discount_amount,
                        'expense_items': expense_items,
                        'punkt_name': punkt_name
                    }

                # Store profit data for this point manager
                all_profit_data[pm_id] = profit_by_date

            return jsonify(all_profit_data), 200

        else:
            return jsonify({'error': 'Метод не разрешен'}), 405

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        traceback.print_exc()  # Output traceback to console or server logs
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


#--------STATISTICS---------------------------------------


#-----------------МЕНЕДЖЕРЫ--------------------------------
def plogin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'punkt_manager_id' not in session:
            return redirect(url_for('punkt_manager_login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/sort_manager')
@plogin_required
def sortpage():
    return render_template("manager_sorting.html")

@app.route('/pay_manager')
@plogin_required
def pay_manager():
    return render_template("pay_managers.html")


@app.route('/punkt_manager/calculate_daily_payment', methods=['GET'])
@plogin_required
def punkt_manager_calculate_daily_payment():
    try:
        punkt_manager_id = session['punkt_manager_id']  # Получаем ID менеджера по пункту из сессии
        current_date = date.today().strftime('%Y-%m-%d')
        print("punkt_manager_id= ", punkt_manager_id)
        query = '''
        SELECT SUM(amount) FROM "Order"
        WHERE pay_date = %s AND punkt_id = (SELECT punkt_id FROM punkt_manager WHERE id = %s)
        '''
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute(query, (current_date, punkt_manager_id))
        total_amount = cur.fetchone()[0]
        if total_amount is None:
            total_amount = 0
        cur.close()
        conn.close()
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/punkt_manager/total_orders_today_cash', methods=['GET'])
@plogin_required
def punkt_manager_total_orders_today_cash():
    try:
        punkt_manager_id = session['punkt_manager_id']  # Получаем ID менеджера по пункту из сессии
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 1 AND DATE(pay_date) = %s AND punkt_id = (SELECT punkt_id FROM punkt_manager WHERE id = %s)
        ''', (date.today(), punkt_manager_id))
        total_amount = cur.fetchone()[0] or 0
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Error retrieving total cash orders for today: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/punkt_manager/total_orders_today_elkart', methods=['GET'])
@plogin_required
def punkt_manager_total_orders_today_elkart():
    try:
        punkt_manager_id = session['punkt_manager_id']  # Получаем ID менеджера по пункту из сессии
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 2 AND DATE(pay_date) = %s AND punkt_id = (SELECT punkt_id FROM punkt_manager WHERE id = %s)
        ''', (date.today(), punkt_manager_id))
        total_amount = cur.fetchone()[0] or 0
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Error retrieving total Elkart orders for today: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/punkt_manager/total_orders_today_mbank', methods=['GET'])
@plogin_required
def punkt_manager_total_orders_today_mbank():
    try:
        punkt_manager_id = session['punkt_manager_id']  # Получаем ID менеджера по пункту из сессии
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 3 AND DATE(pay_date) = %s AND punkt_id = (SELECT punkt_id FROM punkt_manager WHERE id = %s)
        ''', (date.today(), punkt_manager_id))
        total_amount = cur.fetchone()[0] or 0
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Error retrieving total Mbank orders for today: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/punkt_manager/total_orders_today_odengi', methods=['GET'])
@plogin_required
def punkt_manager_total_orders_today_odengi():
    try:
        punkt_manager_id = session['punkt_manager_id']  # Получаем ID менеджера по пункту из сессии
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 4 AND DATE(pay_date) = %s AND punkt_id = (SELECT punkt_id FROM punkt_manager WHERE id = %s)
        ''', (date.today(), punkt_manager_id))
        total_amount = cur.fetchone()[0] or 0
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Error retrieving total Odengi orders for today: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/punkt_manager_orders')
@plogin_required
def punkt_manager_orders():
    return render_template('orders_punkt_manager.html')

@app.route('/punkt_manager/login', methods=['POST', 'GET'])
def punkt_manager_login():
    if 'punkt_manager_id' in session:
        print("Already logged in with punkt_manager_id:", session['punkt_manager_id'])
        return redirect(url_for('punkt_manager_panel'))

    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')

        if not login or not password:
            return render_template('punkt_manager_login.html', error='Please provide both login and password')

        try:
            conn = get_database_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM punkt_manager WHERE login = %s AND password = %s", (login, password))
            manager = cur.fetchone()

            if manager:
                session['punkt_manager_id'] = manager[0]
                print("Logged in, setting session punkt_manager_id to:", manager[0])
                return redirect(url_for('punkt_manager_panel'))
            else:
                return render_template('punkt_manager_login.html', error='Invalid login or password')
        except Exception as e:
            logging.error(f'Error during login: {e}')
            return "An error occurred while processing your request. Please try again later."

    return render_template('punkt_manager_login.html')

@app.route('/punkt_manager/inventarization')
@plogin_required
def inv_punkt_manager():
    return render_template("inventarization_punkt_managers.html")

@app.route('/get_orders_summary_by_status_punkt_managers', methods=['GET'])
@plogin_required
def get_orders_summary_by_status_for_punkt_managers():
    punkt_manager_id = session['punkt_manager_id']

    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                u.id AS user_id,
                u.name || ' ' || u.surname AS client_fio,
                c.phone_num AS phone_number,
                o.comment AS comment,
                COUNT(o.id) AS total_parcel_count,
                SUM(o.massa) AS total_parcel_weight,
                SUM(o.amount) AS total_amount
            FROM "Order" o
            JOIN "User" u ON o.user_id = u.id
            LEFT JOIN "contact" c ON u.id = c.user_id
            WHERE o.order_status_id = 3 AND o.punkt_id = (SELECT punkt_id FROM punkt_manager WHERE id = %s)
            GROUP BY u.id, client_fio, phone_number, o.comment;
        ''', (punkt_manager_id,))

        orders_summary = cur.fetchall()
    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

    summary_data = []
    for summary in orders_summary:
        summary_details = {
            'user_id': summary['user_id'],
            'client_fio': summary['client_fio'],
            'phone_number': summary['phone_number'],
            'comment': summary['comment'],
            'total_parcel_count': summary['total_parcel_count'],
            'total_parcel_weight': summary['total_parcel_weight'],
            'total_amount': summary['total_amount']
        }
        summary_data.append(summary_details)

    return jsonify(summary_data)


# Роут для админ-панели менеджера по пункту
@app.route('/punkt_manager_panel')
@plogin_required
def punkt_manager_panel():
    punkt_manager_id = session['punkt_manager_id']

    conn = get_database_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, surname FROM punkt_manager WHERE id = %s", (punkt_manager_id,))
    punkt_manager = cur.fetchone()
    cur.close()
    conn.close()

    return render_template('punkt_manager_panel.html', punkt_manager=punkt_manager)

# Роут для выхода из админ-панели менеджера по пункту
@app.route('/punkt_manager_logout')
def punkt_manager_logout():
    session.pop('punkt_manager_id', None)
    return redirect(url_for('punkt_manager_login'))

@app.route('/punkt_manager/manage_users')
@plogin_required
def punkt_manager_users():
    punkt_manager_id = session['punkt_manager_id']  # Получаем ID менеджера по пункту из сессии

    conn = get_database_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT id, name, surname, punkt_id, phone_number, login FROM punkt_manager
        WHERE punkt_id = (SELECT punkt_id FROM punkt_manager WHERE id = %s)
    ''', (punkt_manager_id,))
    users = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('manage_users_punkt.html', users=users)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'manager_id' not in session:
            return redirect(url_for('manager_login'))
        return f(*args, **kwargs)
    return decorated_function

# Роут для страницы заказов менеджера
@app.route('/manager_orders')
@login_required
def manager_orders():
    return render_template('orders_manger.html')

@app.route('/manager/login', methods=['POST', 'GET'])
def manager_login():
    if 'manager_id' in session:
        return redirect(url_for('manager_panel'))  # Перенаправляем на панель, если менеджер уже вошел в систему
    
    if 'login' not in request.form or 'password' not in request.form:
        return render_template('manager_login.html', error='Please provide both login and password')
    
    login = request.form['login']
    password = request.form['password']

    try:
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM manager WHERE login = %s AND password = %s", (login, password))
        manager = cur.fetchone()

        if manager:
            session['manager_id'] = manager[0]
            return redirect(url_for('manager_panel'))
        else:
            return render_template('manager_login.html', error='Invalid login or password')
    except Exception as e:
        return "An error occurred while processing your request. Please try again later."



@app.route('/punkt_manager/get_all_orders', methods=['GET'])
@plogin_required
def get_orders_for_punkt_manager():
    punkt_manager_id = session['punkt_manager_id']

    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                o.id,
                o.data_send_from_china, 
                o.track_code, 
                os.name AS order_status, 
                o.user_tarif,
                o.massa, 
                o.comment, 
                o.sort_date, 
                o.amount,
                o.payment_status,
                u.name || ' ' || u.surname AS client_fio, 
                u.id AS user_id, 
                p.name AS punkt_name, 
                ct.phone_num, 
                ct.extra_phone_num, 
                ct.tg_nickname, 
                ct.email,
                o.discount_amount
            FROM "Order" o
            JOIN Order_status os ON o.order_status_id = os.id
            LEFT JOIN "User" u ON o.user_id = u.id
            LEFT JOIN Punkt p ON u.punkt_id = p.id
            LEFT JOIN Contact ct ON u.id = ct.user_id
            WHERE p.id = (SELECT punkt_id FROM punkt_manager WHERE id = %s);
        ''', (punkt_manager_id,))

        orders = cur.fetchall()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    orders_data = []
    for order in orders:
        order_details = {
            'id': order['id'],
            'data_send_from_china': order['data_send_from_china'].strftime('%Y-%m-%d') if order['data_send_from_china'] else 'Не указано',
            'track_code': order['track_code'],
            'order_status': order['order_status'],
            'user_tarif': str(order['user_tarif']),
            'massa': order['massa'],
            'comment': order['comment'],
            'client_fio': order['client_fio'],
            'user_id': order['user_id'],
            'city_name': order['punkt_name'],
            'phone_num': order['phone_num'],
            'extra_phone_num': order['extra_phone_num'],
            'tg_nickname': order['tg_nickname'],
            'email': order['email'],
            'sort_date': order['sort_date'].strftime('%Y-%m-%d %H:%M:%S') if order['sort_date'] else 'Не указано',
            'amount': str(order['amount']),
            'discount_amount': str(order['discount_amount']),
            'payment_status': order['payment_status']
        }
        orders_data.append(order_details)

    return jsonify(orders_data)


@app.route('/punkt_manager/get_all_users', methods=['GET'])
@plogin_required
def get_all_users_for_punkt_managers():
    punkt_manager_id = session.get('punkt_manager_id')
    print(punkt_manager_id)
    if not punkt_manager_id:
        logging.error("No punkt_manager_id in session")
        return redirect(url_for('punkt_manager_login'))

    print("punkt_manager_id:", punkt_manager_id)
    logging.info(f'punkt_manager_id: {punkt_manager_id}')

    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                u.id, u.name, u.surname, u.user_tarif,
                p.name AS punkt_name, 
                ct.phone_num, ct.extra_phone_num, ct.tg_nickname, ct.email
            FROM "User" u
            LEFT JOIN punkt p ON u.punkt_id = p.id
            LEFT JOIN contact ct ON u.id = ct.user_id
            WHERE u.punkt_id = (SELECT punkt_id FROM punkt_manager WHERE id = %s);
        ''', (punkt_manager_id,))

        users = cur.fetchall()
        print(users)
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    users_data = []
    for user in users:
        user_details = {
            'id': user['id'],
            'name': user['name'],
            'surname': user['surname'],
            'user_tarif': user['user_tarif'],
            'punkt_name': user['punkt_name'],
            'phone_num': user['phone_num'],
            'extra_phone_num': user['extra_phone_num'],
            'tg_nickname': user['tg_nickname'],
            'email': user['email']
        }
        users_data.append(user_details)

    return jsonify(users_data)


# Роут для админ-панели менеджера
@app.route('/manager_panel')
@login_required
def manager_panel():
    manager_id = session['manager_id']

    conn = get_database_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, surname FROM manager WHERE id = %s", (manager_id,))
    manager = cur.fetchone()
    cur.close()
    conn.close()

    return render_template('manager_panel.html', manager=manager)

# Роут для выхода из админ-панели менеджера
@app.route('/manager_logout')
def manager_logout():
    session.pop('manager_id', None)
    return redirect(url_for('manager_login'))


@app.route('/manager/get_all_orders', methods=['GET'])
@login_required
def get_orders_for_manager():
    manager_id = session['manager_id']

    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                o.id,
                o.data_send_from_china, 
                o.track_code, 
                os.name AS order_status, 
                o.user_tarif,
                o.massa, 
                o.comment, 
                o.sort_date, 
                o.amount,
                o.payment_status,
                u.name || ' ' || u.surname AS client_fio, 
                u.id AS user_id, 
                c.name AS city_name, 
                ct.phone_num, 
                ct.extra_phone_num, 
                ct.tg_nickname, 
                ct.email,
                o.discount_amount
            FROM "Order" o
            JOIN Order_status os ON o.order_status_id = os.id
            LEFT JOIN "User" u ON o.user_id = u.id
            LEFT JOIN City c ON u.city_id = c.id
            LEFT JOIN Contact ct ON u.id = ct.user_id
            WHERE c.id = (SELECT city_id FROM manager WHERE id = %s);
        ''', (manager_id,))

        orders = cur.fetchall()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    orders_data = []
    for order in orders:
        order_details = {
            'id': order['id'],
            'data_send_from_china': order['data_send_from_china'].strftime('%Y-%m-%d') if order['data_send_from_china'] else 'Не указано',
            'track_code': order['track_code'],
            'order_status': order['order_status'],
            'user_tarif': str(order['user_tarif']),
            'massa': order['massa'],
            'comment': order['comment'],
            'client_fio': order['client_fio'],
            'user_id': order['user_id'],
            'city_name': order['city_name'],
            'phone_num': order['phone_num'],
            'extra_phone_num': order['extra_phone_num'],
            'tg_nickname': order['tg_nickname'],
            'email': order['email'],
            'sort_date': order['sort_date'].strftime('%Y-%m-%d %H:%M:%S') if order['sort_date'] else 'Не указано',
            'amount': str(order['amount']),
            'discount_amount': str(order['discount_amount']),
            'payment_status':order['payment_status']
        }
        orders_data.append(order_details)

    return jsonify(orders_data)


@app.route('/manager/manage_users')
@login_required
def manager_users():
    return render_template('manage_users_regions.html')

@app.route('/manager/get_all_users', methods=['GET'])
@login_required
def get_all_users_for_managers():
    manager_id = session['manager_id']

    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                u.id, u.name, u.surname, u.user_tarif,
                c.name AS city_name, 
                ct.phone_num, ct.extra_phone_num, ct.tg_nickname, ct.email
            FROM "User" u
            LEFT JOIN City c ON u.city_id = c.id
            LEFT JOIN Contact ct ON u.id = ct.user_id
            WHERE u.city_id = (SELECT city_id FROM manager WHERE id = %s);
        ''', (manager_id,))

        users = cur.fetchall()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    users_data = []
    for user in users:
        user_details = {
            'id': user['id'],
            'name': user['name'],
            'surname': user['surname'],
            'user_tarif': user['user_tarif'],
            'city_name': user['city_name'],
            'phone_num': user['phone_num'],
            'extra_phone_num': user['extra_phone_num'],
            'tg_nickname': user['tg_nickname'],
            'email': user['email']
        }
        users_data.append(user_details)
        

    return jsonify(users_data)

@app.route('/manager/inventarization')
@login_required
def inv_manager():
    return render_template("inventarization_managers.html")

@app.route('/get_orders_summary_by_status_managers', methods=['GET'])
@login_required
def get_orders_summary_by_status_for_managers():
    manager_id = session['manager_id']

    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                u.id AS user_id,
                u.name || ' ' || u.surname AS client_fio,
                c.phone_num AS phone_number,
                o.comment AS comment,
                COUNT(o.id) AS total_parcel_count,
                SUM(o.massa) AS total_parcel_weight,
                SUM(o.amount) AS total_amount
            FROM "Order" o
            JOIN "User" u ON o.user_id = u.id
            LEFT JOIN "contact" c ON u.id = c.user_id
            WHERE o.order_status_id = 3 AND o.city_id = (SELECT city_id FROM manager WHERE id = %s)
            GROUP BY u.id, client_fio, phone_number, o.comment;
        ''', (manager_id,))

        orders_summary = cur.fetchall()
    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

    summary_data = []
    for summary in orders_summary:
        summary_details = {
            'user_id': summary['user_id'],
            'client_fio': summary['client_fio'],
            'phone_number': summary['phone_number'],
            'comment': summary['comment'],
            'total_parcel_count': summary['total_parcel_count'],
            'total_parcel_weight': summary['total_parcel_weight'],
            'total_amount': summary['total_amount']
        }
        summary_data.append(summary_details)

    return jsonify(summary_data)

@app.route('/manager/calculate_daily_payment', methods=['GET'])
@login_required
def manager_calculate_daily_payment():
    try:
        manager_id = session['manager_id']  # Получаем ID менеджера из сессии
        current_date = date.today().strftime('%Y-%m-%d')
        query = '''
        SELECT SUM(amount) FROM "Order"
        WHERE pay_date = %s AND city_id = (SELECT city_id FROM manager WHERE id = %s)
        '''
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute(query, (current_date, manager_id))
        total_amount = cur.fetchone()[0]
        if total_amount is None:
            total_amount = 0
        cur.close()
        conn.close()
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/manager/total_orders_today_cash', methods=['GET'])
@login_required
def manager_total_orders_today_cash():
    try:
        manager_id = session['manager_id']  # Получаем ID менеджера из сессии
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 1 AND DATE(pay_date) = %s AND city_id = (SELECT city_id FROM manager WHERE id = %s)
        ''', (date.today(), manager_id))
        total_amount = cur.fetchone()[0] or 0
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Error retrieving total cash orders for today: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/manager/total_orders_today_elkart', methods=['GET'])
@login_required
def manager_total_orders_today_elkart():
    try:
        manager_id = session['manager_id']  # Получаем ID менеджера из сессии
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 2 AND DATE(pay_date) = %s AND city_id = (SELECT city_id FROM manager WHERE id = %s)
        ''', (date.today(), manager_id))
        total_amount = cur.fetchone()[0] or 0
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Error retrieving total Elkart orders for today: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/manager/total_orders_today_mbank', methods=['GET'])
@login_required
def manager_total_orders_today_mbank():
    try:
        manager_id = session['manager_id']  # Получаем ID менеджера из сессии
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 3 AND DATE(pay_date) = %s AND city_id = (SELECT city_id FROM manager WHERE id = %s)
        ''', (date.today(), manager_id))
        total_amount = cur.fetchone()[0] or 0
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Error retrieving total Mbank orders for today: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/manager/total_orders_today_odengi', methods=['GET'])
@login_required
def manager_total_orders_today_odengi():
    try:
        manager_id = session['manager_id']  # Получаем ID менеджера из сессии
        conn = get_database_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT SUM(amount) FROM "Order"
            WHERE payment_type_id = 4 AND DATE(pay_date) = %s AND city_id = (SELECT city_id FROM manager WHERE id = %s)
        ''', (date.today(), manager_id))
        total_amount = cur.fetchone()[0] or 0
        return jsonify({'total_amount': total_amount})
    except Exception as e:
        logging.error(f'Error retrieving total Odengi orders for today: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()


#--------BOT----------------
conn = psycopg2.connect(
    host="176.126.166.199",
    port="5432",
    dbname="cargo_mango",
    user="amin",
    password="1gJx7y8kQ5O1"
)

import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
@app.route('/register_webhook', methods=['POST'])
def handle_data():
    data = request.json

    # Log the received JSON data
    logging.info(f"Received JSON data: {data}")

    # Extract and log each field
    user_id = data.get('user_id')
    name = data.get('name')
    surname = data.get('surname')
    phone_num = data.get('phone_num')
    region_id = data.get('region_id')
    extra_phone_num = data.get('extra_phone_num')
    city_id = data.get('city_id')
    punkt_vidach = data.get('punkt_vidach')
    tg_nickname = data.get('tg_nickname') or "not"
    tg_user_id = data.get('tg_user_id')

    logging.info(f"user_id: {user_id}")
    logging.info(f"name: {name}")
    logging.info(f"surname: {surname}")
    logging.info(f"phone_num: {phone_num}")
    logging.info(f"region_id: {region_id}")
    logging.info(f"extra_phone_num: {extra_phone_num}")
    logging.info(f"city_id: {city_id}")
    logging.info(f"punkt_vidach: {punkt_vidach}")
    logging.info(f"tg_nickname: {tg_nickname}")
    logging.info(f"tg_user_id: {tg_user_id}")

    # Convert region_id to None if it's "Null"
    if region_id == 'Null':
        region_id = None

    # Validate required fields
    required_fields = [name, surname, phone_num, city_id, punkt_vidach, tg_user_id]
    if not all(required_fields):
        missing_fields = [field_name for field_name, field_value in zip(
            ["name", "surname", "phone_num", "city_id", "punkt_vidach", "tg_user_id"], required_fields) if not field_value]
        logging.error(f"Missing fields: {missing_fields}")
        return jsonify({'error': f'Missing fields: {", ".join(missing_fields)}'}), 400

    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        default_value_for_user_tarif = 350

        cursor.execute("SELECT MAX(id) FROM \"User\"")
        max_id = cursor.fetchone()[0]
        next_id = max_id + 1 if max_id is not None else 1
        logging.info('Next user ID: %d', next_id)

        # Validate city_id
        cursor.execute("SELECT id FROM city WHERE id = %s", (city_id,))
        if cursor.fetchone() is None:
            logging.error("Invalid city_id: %s", city_id)
            return jsonify({'error': 'city_id does not exist in city table'}), 400

        # Validate region_id if it's not None
        if region_id is not None:
            cursor.execute("SELECT id FROM region WHERE id = %s", (region_id,))
            if cursor.fetchone() is None:
                logging.error("Invalid region_id: %s", region_id)
                return jsonify({'error': 'region_id does not exist in region table'}), 400

        # Validate punkt_vidach
        cursor.execute("SELECT id FROM punkt WHERE id = %s AND city_id = %s", (punkt_vidach, city_id))
        if cursor.fetchone() is None:
            logging.error("Invalid punkt_vidach: %s for city_id: %s", punkt_vidach, city_id)
            return jsonify({'error': 'punkt_vidach does not exist in punkt table or does not match city_id'}), 400

        # Insert into User
        cursor.execute(
            "INSERT INTO \"User\" (id, name, surname, user_tarif, city_id, region_id, punkt_id) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id", 
            (next_id, name, surname, default_value_for_user_tarif, city_id, region_id, punkt_vidach)
        )
        inserted_user_id = cursor.fetchone()[0]
        logging.info(f"Inserted into User table with ID: {inserted_user_id}")

        # Insert into Contact
        cursor.execute(
            "INSERT INTO Contact (phone_num, extra_phone_num, tg_nickname, user_id, tg_user_id) VALUES (%s, %s, %s, %s, %s)", 
            (phone_num, extra_phone_num, tg_nickname, next_id, tg_user_id)
        )
        logging.info(f"Inserted into Contact table with User ID: {next_id}")

        # Commit changes to the database
        conn.commit()

        logging.info(f"User {name} {surname} inserted with ID {next_id}")
        return jsonify({'success': True}), 200
    except Exception as e:
        # Rollback transaction in case of error
        conn.rollback()
        logging.error("Error occurred: %s", e)
        return jsonify({'error': str(e)}), 500
    finally:
        # Close cursor and connection
        cursor.close()
        conn.close()

import secrets
from aiogram.types.web_app_info import WebAppInfo

def generate_auth_token():
    return secrets.token_urlsafe(16)

def verify_auth_token(token):
    if not token:
        return False
    if not token.isalnum():
        return False

    return True

@app.before_request 
def check_auth_token():
    if 'auth_token' in request.args:
        auth_token = request.args.get('auth_token')
        # Проверяем токен
        if not verify_auth_token(auth_token):
            return 'Неверный токен!', 401

def send_url(user_tg_id, redirect_url):
    try:
        token_api = "AXLiBlf82MwQH5Ft66KZcFaBhT92lATO"
        redirect_url = redirect_url.replace("http://", "https://")
        url = f"https://api.puzzlebot.top/?token={token_api}&method=tg.sendMessage"
        payload = {
            "chat_id": user_tg_id,
            "text": "Откройте ссылку",
            "reply_markup": {
                "inline_keyboard": [[
                    {
                        "text": "Open Url",
                        "web_app": {"url": redirect_url}
                    }
                ]]
            }
        }

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)
        print(response.text)
        if response.status_code == 200:
            print("Сообщение успешно отправлено")
            # Вызываем функцию для изменения переменной
            change_perem(user_tg_id, redirect_url)
        else:
            print("Произошла ошибка при отправке сообщения")

    except Exception as e:
        print('error:', str(e))



app.logger.setLevel(logging.DEBUG)
import secrets
from aiogram.types.web_app_info import WebAppInfo

@app.route('/login_bot', methods=['POST', 'GET'])
def login_bot():
    print("Reached login_bot endpoint")  # Проверяем, достигается ли эндпоинт
    if request.method == 'POST':
        data = request.json 
        print("data") # Получаем данные из JSON тела запроса
        print(data)
        if data:
            user_tg_id = data.get('tg_user_id')
            user_login = data.get('user_login')
            password = data.get('password')
            print("user_tg_id", user_tg_id )
            # Проверка учетных данных
            if check_user_credentials(user_login, password):
                redirect_url = url_for('user_bot_page', user_id=user_login, _external=True)
                print("redirect_url", redirect_url)
                send_url(user_tg_id, redirect_url)
                return jsonify({'success': True, 'redirect_url': redirect_url})
            else:
                # Если учетные данные неверны, возвращаем ошибку
                return jsonify({'success': False, 'error': 'Invalid credentials. Please try again.'})

    return render_template('sign-in.html')

@app.route('/user_bot')
def user_bot_page():
    user_id = request.args.get('user_id')
    if user_id:
        orders_by_status = get_orders_by_status_for_user(user_id)
        order_counts = get_order_counts_by_status(user_id)
        if orders_by_status and order_counts:
            return render_template('user_bot.html', user_id=user_id, orders_by_status=orders_by_status, order_counts=order_counts)
        else:
            return 'Ошибка: У вас пока нет посылок', 404
    else:
        return 'User ID not provided', 400
   

def check_user_credentials(user_id, password):
    connection = get_database_connection()
    cursor = connection.cursor()
    
    cursor.execute('SELECT name, phone_num FROM "User" INNER JOIN Contact ON "User".id = Contact.user_id WHERE "User".id = %s', (user_id,))
    user_data = cursor.fetchone()
    
    if user_data:
        name, phone_num = user_data
        if password == phone_num:  
            # Сохраняем имя пользователя в сессии
            session['user_id'] = user_id
            session['username'] = name
            return True
    
    return False

def change_perem(user_tg_id, redirect_url):
    try:
        token_api = "AXLiBlf82MwQH5Ft66KZcFaBhT92lATO"
        url = f"https://api.puzzlebot.top/?token={token_api}&method=variableChange"
        redirect_url = f'"{redirect_url}"'
        print(redirect_url)

        payload = {
            "variable": "personal_url",
            "expression": redirect_url,
            "user_id": user_tg_id
        }

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.get(url, json=payload, headers=headers)
        print(response.text)
        if response.status_code == 200:
            print("Переменная успешно изменилась")
        else:
            print("Произошла ошибка при изменении переменной")

    except Exception as e:
        print('error:', str(e))



def update_status_send_tg():
    try:
        conn = psycopg2.connect(
            host="5.59.233.100",
            dbname="cargo_express",
            user="amin",
            password="6US3F5T5aVtB"
        )
        cursor = conn.cursor()

        update_query = """
            UPDATE "Order" 
            SET status_send_tg = CASE
                WHEN order_status_id = 1 AND status_send_tg IS NULL THEN 1
                WHEN order_status_id = 3 AND status_send_tg =  1 THEN 3
                WHEN order_status_id = 4 AND status_send_tg = 3 THEN 4
                ELSE status_send_tg
            END
            WHERE order_status_id IN (1, 3, 4);
        """

        cursor.execute(update_query)
        conn.commit()
        
        cursor.close()
        conn.close()

        print("Статусы успешно обновлены")
    except (Exception, psycopg2.Error) as error:
        print("Ошибка при обновлении статусов:", error)


import logging

# Настройка логгера
logging.basicConfig(level=logging.INFO)

@app.route('/send_message_tg', methods=['POST'])
def main2():
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        order_status_id = request.json.get('order_status_id')
        logging.info("order_status_id=%s", order_status_id)
        
        if order_status_id == 1:
            query = """
            SELECT o.user_id, c.tg_user_id, COUNT(o.id) as num_packages, o.status_send_tg, u.punkt_id, pm.address, pm.phone_number
            FROM "Order" o
            LEFT JOIN Contact c ON o.user_id = c.user_id
            LEFT JOIN "User" u ON o.user_id = u.id
            LEFT JOIN punkt_manager pm ON u.punkt_id = pm.punkt_id
            WHERE o.order_status_id = 1 AND (o.status_send_tg IS NULL OR o.status_send_tg != 1) 
            GROUP BY o.user_id, c.tg_user_id, o.status_send_tg, u.punkt_id, pm.address, pm.phone_number;
            """
            cursor.execute(query)
            results = cursor.fetchall()
            logging.info("res: %s", results)
            for user_id, tg_user_id, num_packages, status_send_tg, punkt_id, address, manager_phone in results:
                if tg_user_id:  # Убедимся, что tg_user_id не пустой
                    text = (
                        f"Здравствуйте! 👋\n\n"
                        f"У вас {num_packages} посылок в пути. 📦\n\n"
                        f"Адрес пункта выдачи: {address},\n"
                        f"Контактный номер менеджера: {manager_phone}"
                    )
                    send_message_with_delay(tg_user_id, text, user_id)
                    time.sleep(1)  # Задержка после отправки сообщения
                else:
                    logging.info(f"Нет tg_user_id для user_id {user_id}")

        elif order_status_id == 3:
            query = """
            SELECT o.user_id, c.tg_user_id, COUNT(o.id) as num_packages, SUM(o.amount) as total_amount, SUM(o.massa) as total_mass, o.status_send_tg, u.punkt_id, pm.address, pm.phone_number
            FROM "Order" o
            LEFT JOIN Contact c ON o.user_id = c.user_id
            LEFT JOIN "User" u ON o.user_id = u.id
            LEFT JOIN punkt_manager pm ON u.punkt_id = pm.punkt_id
            WHERE o.order_status_id = 3 AND DATE(o.sort_date) = CURRENT_DATE AND (o.status_send_tg IS NULL OR o.status_send_tg != 3) 
            GROUP BY o.user_id, c.tg_user_id, o.status_send_tg, u.punkt_id, pm.address, pm.phone_number;
            """
            cursor.execute(query)
            results = cursor.fetchall()
            logging.info("results3: %s", results)
            for user_id, tg_user_id, num_packages, total_amount, total_mass, status_send_tg, punkt_id, address, manager_phone in results:
                if tg_user_id:  # Убедимся, что tg_user_id не пустой
                    text = (
                        f"Здравствуйте! 👋\n\n"
                        f"У вас {num_packages} посылок с общей стоимостью {total_amount} и общим весом {total_mass} кг готовы к выдаче.📦\n\n "
                        f"Ваш клиентский код: {user_id}.\n\n Адрес пункта выдачи: {address},\n\n Контактный номер менеджера: {manager_phone}"
                    )
                    send_message_with_delay(tg_user_id, text, user_id)
                    time.sleep(6)  # Задержка после отправки сообщения

        elif order_status_id == 4:
            query = """
            SELECT o.user_id, c.tg_user_id, COUNT(o.id) as num_packages, SUM(o.amount) as total_amount, o.status_send_tg, u.punkt_id, pm.address, pm.phone_number
            FROM "Order" o
            LEFT JOIN Contact c ON o.user_id = c.user_id
            LEFT JOIN "User" u ON o.user_id = u.id
            LEFT JOIN punkt_manager pm ON u.punkt_id = pm.punkt_id
            WHERE o.order_status_id = 4 AND DATE(o.pay_date) = CURRENT_DATE AND (o.status_send_tg IS NULL OR o.status_send_tg != 4) 
            GROUP BY o.user_id, c.tg_user_id, o.status_send_tg, u.punkt_id, pm.address, pm.phone_number;
            """
            cursor.execute(query)
            results = cursor.fetchall()
            logging.info("res: %s", results)
            for user_id, tg_user_id, num_packages, total_amount, status_send_tg, punkt_id, address, manager_phone in results:
                if tg_user_id:  # Убедимся, что tg_user_id не пустой
                    text = (
                        f"Здравствуйте! 👋\n\nУ вас оплачено {num_packages} посылок на сумму {total_amount} 💵. Благодарим за сотрудничество!,\nКонтактный номер менеджера: {manager_phone}\n\n Если у вас возникли вопросы или вам нужна помощь, пожалуйста, свяжитесь с нашим менеджером. Мы всегда готовы помочь!"
                    )
                    send_message_with_delay(tg_user_id, text, user_id)
                    time.sleep(6)  # Задержка после отправки сообщения
                else:
                    logging.info(f"Нет tg_user_id для user_id {user_id}")

        else:
            # Unknown order_status_id
            return jsonify({'message': 'Unknown order_status_id'}), 400

        update_status_send_tg()

        cursor.close()
        conn.close()

        return jsonify({'message': 'Сообщение успешно отправлено'})

    except (Exception, psycopg2.Error) as error:
        logging.error("Ошибка при получении данных из базы данных: %s", error)
        return jsonify({'message': 'error'}), 500


def send_message_with_delay(chat_id, text, user_id):
    token_api = "AXLiBlf82MwQH5Ft66KZcFaBhT92lATO"
    login_url = f"https://china-express-kg.com/user_bot?user_id={user_id}"
    url = f"https://api.puzzlebot.top?method=tg.sendMessage&token={token_api}"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {
            "inline_keyboard": [[
                {
                    "text": "Подробнее 👀",
                    "url": login_url
                }
            ]]
        }
    }
    headers = {
        "Content-Type": "application/json"
    }
    
    # Обработка исключений при отправке запроса
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()  # Проверка статуса ответа
        logging.info("Сообщение успешно отправлено")
        print("url ",url )
        return True
    except requests.exceptions.RequestException as e:
        logging.error("Произошла ошибка при отправке сообщения func: %s", e)
        return False
    


#-------ОТЧЕТЫ-------------------------------

@app.route('/reports')
@admin_login_required
def reports_page():
    return render_template("reports.html")


@app.route('/orders_by_user')
@admin_login_required
def orders_by_user():
    # Получаем даты начала и конца периода из параметров запроса
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    try:
        print("Received parameters: start_date =", start_date, ", end_date =", end_date)

        conn = get_database_connection()
        print("Database connection established")

        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT
                u.id AS user_id,
                u.name || ' ' || u.surname AS client_name,
                c.name AS city,
                u.user_tarif AS user_tariff,
                SUM(o.amount) AS total_amount,
                COUNT(o.id) AS order_count
            FROM "User" u
            LEFT JOIN "Order" o ON u.id = o.user_id
            LEFT JOIN city c ON u.city_id = c.id
            WHERE o.order_status_id = 4
                AND o.pay_date BETWEEN %s AND %s -- Условие для выбора заказов по дате оплаты в выбранном периоде
            GROUP BY u.id, client_name, city, user_tariff
            ORDER BY order_count DESC;
        ''', (start_date, end_date))

        print("SQL query executed")

        discount_by_user = cur.fetchall()
        if not discount_by_user:
            print("No discount data found")

    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()
        print("Database connection closed")

    result = []
    for discount_info in discount_by_user:
        user_discount = {
            'user_id': discount_info['user_id'],
            'client_name': discount_info['client_name'],
            'city': discount_info['city'],
            'user_tariff': discount_info['user_tariff'],
            'total_amount': discount_info['total_amount'],
            'total_orders' : discount_info['order_count']
        }
        result.append(user_discount)
        print("result", result)

    return jsonify(result)




@app.route('/stat_sales')
@admin_login_required
def stat_sales():
    return render_template("saleuser.html")


@app.route('/top_10_clients')
@admin_login_required
def top_10_clients():
    current_date = datetime.now()
    start_date = current_date - timedelta(days=30)
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT
                u.id AS user_id,
                u.name || ' ' || u.surname AS client_name,
                c.name AS city,
                u.user_tarif AS user_tariff,
                SUM(o.amount) AS total_amount,
                COUNT(o.id) AS order_count
            FROM "User" u
            LEFT JOIN "Order" o ON u.id = o.user_id
            LEFT JOIN city c ON u.city_id = c.id
            WHERE o.order_status_id = 4
                AND o.pay_date >= %s  -- Учитываем только заказы, сделанные за последние 30 дней
            GROUP BY u.id, client_name, city, user_tariff
            ORDER BY total_amount DESC
            LIMIT 10;
        ''', (start_date,))

        top_clients = cur.fetchall()
        if not top_clients:
            print("No data found")

    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500

    finally:
        cur.close()
        conn.close()

    result = []
    for client_info in top_clients:
        client_data = {
            'user_id': client_info['user_id'],
            'client_name': client_info['client_name'],
            'city': client_info['city'],
            'user_tariff': client_info['user_tariff'],
            'total_amount': client_info['total_amount'],
            'total_orders': client_info['order_count']
        }
        result.append(client_data)

    return jsonify(result)

import plotly.graph_objs as go

@app.route('/finstat')
@admin_login_required
def finstat():
    return render_template("finstat.html")

@app.route('/expenses_by_category_last_30_days')
@admin_login_required
def expenses_by_category_last_30_days():
    try:
        # Определяем текущую дату и дату, предшествующую ей на 30 дней
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)

        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                c.name AS category_name, 
                SUM(e.amount) AS total_amount
            FROM 
                public.expenses e
            LEFT JOIN 
                public.cost_item c ON e.cost_item_id = c.id
            WHERE 
                e.expense_date BETWEEN %s AND %s
            GROUP BY 
                c.name
            ORDER BY 
                total_amount DESC;
        ''', (start_date, end_date))

        expenses_by_category = cur.fetchall()
        if not expenses_by_category:
            print("No data found")

    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

    result = []
    for category_info in expenses_by_category:
        category_data = {
            'category_name': category_info['category_name'],
            'total_amount': category_info['total_amount']
        }
        result.append(category_data)

    return jsonify(result)

@app.route('/income_by_item_last_30_days')
@admin_login_required
def income_by_item_last_30_days():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT
                i.id,
                i.name AS item_name,
                i.amount,
                i.date,
                i.comment,
                i.income_item_id,
                ii.name AS income_item_name
            FROM public.income i
            LEFT JOIN income_item ii ON i.income_item_id = ii.id
            WHERE i.date >= NOW() - INTERVAL '30 days'
        ''')

        income_data = cur.fetchall()
        if not income_data:
            print("No data found")

    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

    result = []
    for income_entry in income_data:
        entry_data = {
            'id': income_entry['id'],
            'item_name': income_entry['item_name'],
            'amount': income_entry['amount'],
            'date': income_entry['date'].strftime('%Y-%m-%d'),
            'comment': income_entry['comment'],
            'income_item_id': income_entry['income_item_id'],
            'income_item_name': income_entry['income_item_name']
        }
        result.append(entry_data)

    return jsonify(result)

@app.route('/sales_by_payment_type')
@admin_login_required
def sales_by_payment_type():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            
            SELECT
                pt.id AS payment_type_id,
                pt.name AS payment_type_name,
                SUM(o.amount) AS total_sales
            FROM
                public."Order" o
            LEFT JOIN
                payment_type pt ON o.payment_type_id = pt.id
            WHERE
                o.sort_date >= CURRENT_DATE - INTERVAL '30 days'and o.order_status_id=4
            GROUP BY
                pt.id, pt.name;
        ''')

        sales_data = cur.fetchall()
        if not sales_data:
            print("No sales data found")

    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

    result = []
    for sale_info in sales_data:
        sale_data = {
            'payment_type_id': sale_info['payment_type_id'],
            'payment_type_name': sale_info['payment_type_name'],
            'total_sales': sale_info['total_sales']
        }
        result.append(sale_data)

    return jsonify(result)



@app.route('/sales_by_month')
@admin_login_required
def sales_by_month():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT
                to_char(sort_date, 'YYYY-MM') AS month,
                SUM(amount) AS total_sales
            FROM
                public."Order"
            WHERE
                order_status_id = 4 AND
                sort_date >= CURRENT_DATE - INTERVAL '3 months'
            GROUP BY
                month
            ORDER BY
                month;
        ''')

        sales_data = cur.fetchall()
        if not sales_data:
            print("No sales data found")

    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

    result = []
    for sale_info in sales_data:
        sale_data = {
            'month': sale_info['month'],
            'total_sales': sale_info['total_sales']
        }
        result.append(sale_data)

    return jsonify(result)


@app.route('/calculate_discount_by_user', methods=['GET'])
@admin_login_required
def calculate_discount_by_user():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                u.id AS user_id,
                u.name || ' ' || u.surname AS client_name,
                c.name AS city,
                u.user_tarif AS user_tariff,
                SUM(o.discount_amount) AS total_discount
            FROM "User" u
            LEFT JOIN "Order" o ON u.id = o.user_id
            LEFT JOIN city c ON u.city_id = c.id
            GROUP BY u.id, client_name, city, user_tariff
            ORDER BY total_discount DESC; -- Сортировка по убыванию суммы скидки
        ''')

        discount_by_user = cur.fetchall()
        if not discount_by_user:
            print("No discount data found")

    except Exception as e:
        logging.error(f'Database query error: {e}')
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

    result = []
    for discount_info in discount_by_user:
        user_discount = {
            'user_id': discount_info['user_id'],
            'client_name': discount_info['client_name'],
            'city': discount_info['city'],
            'user_tariff': discount_info['user_tariff'],
            'total_discount': discount_info['total_discount']
        }
        result.append(user_discount)

    return jsonify(result)


@app.route('/add_waybill', methods=['POST'])
@admin_login_required
def add_waybill():
    try:
        conn = get_database_connection()
        cur = conn.cursor()
        data = request.json
        # Извлекаем данные из запроса
        sending_date = data.get('sending_date')
        marking = data.get('marking')
        box_count = data.get('box_count')
        total_weight = data.get('total_weight')
        cub = data.get('volume')
        density = data.get('density')
        tariff = data.get('tariff')
        packaging_cost = data.get('packaging_cost')
        total_amount = data.get('total_amount')
        status_id = data.get('status_id')

        # Вставляем данные в таблицу накладных
        cur.execute('''
            INSERT INTO ChinaWaybills (sending_date, marking, box_count, total_weight, volume, density, tariff, packaging_cost, total_amount, status_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (sending_date, marking, box_count, total_weight, cub, density, tariff, packaging_cost, total_amount, status_id))

        conn.commit()
        
        return jsonify({'message': 'Накладная успешно добавлена'}), 201
    except Exception as e:
        logging.error(f'Ошибка при добавлении накладной: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/delete_waybill/<int:waybill_id>', methods=['DELETE'])
@admin_login_required
def delete_waybill(waybill_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Удаляем накладную по указанному ID
        cur.execute('DELETE FROM ChinaWaybills WHERE id = %s', (waybill_id,))
        affected_rows = cur.rowcount  

        conn.commit()
        
        return jsonify({'message': f'{affected_rows} накладных удалено'}), 200
    except Exception as e:
        logging.error(f'Ошибка при удалении накладной: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/get_all_waybills', methods=['GET'])
@admin_login_required
def get_all_waybills():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Получаем все накладные из базы данных
        cur.execute('SELECT * FROM ChinaWaybills')
        waybills = cur.fetchall()

        # Преобразуем результат в список словарей для удобного вывода
        waybill_list = []
        for waybill in waybills:
            waybill_dict = {
                'id': waybill[0],
                'date_of_dispatch': waybill[1],
                'marking': waybill[2],
                'number_of_boxes': waybill[3],
                'total_weight': waybill[4],
                'cub': waybill[5],
                'density': waybill[6],
                'tariff': waybill[7],
                'packaging_cost': waybill[8],
                'total_amount': waybill[9],
                'status_id': waybill[10]
            }
            waybill_list.append(waybill_dict)

        return jsonify(waybill_list), 200
    except Exception as e:
        logging.error(f'Ошибка при получении накладных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/change_waybill_status/<int:waybill_id>', methods=['PUT'])
@admin_login_required
def change_waybill_status(waybill_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Проверяем, существует ли накладная с указанным идентификатором
        cur.execute('SELECT * FROM ChinaWaybills WHERE id = %s', (waybill_id,))
        waybill = cur.fetchone()
        if not waybill:
            return jsonify({'error': 'Накладная с указанным идентификатором не найдена'}), 404

        # Изменяем статус накладной на 4 (доставлено)
        cur.execute('UPDATE ChinaWaybills SET status_id = 4 WHERE id = %s', (waybill_id,))
        conn.commit()

        return jsonify({'success': 'Статус накладной успешно изменен на "Доставлено"'}), 200
    except Exception as e:
        logging.error(f'Ошибка при изменении статуса накладной: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/add_waybillb', methods=['POST'])
@admin_login_required
def add_waybillb():
    try:
        conn = get_database_connection()
        cur = conn.cursor()
        data = request.json
        # Извлекаем данные из запроса
        sending_date = data.get('sending_date')
        marking = data.get('marking')
        box_count = data.get('box_count')
        total_weight = data.get('total_weight')
        cub = data.get('volume')
        density = data.get('density')
        tariff = data.get('tariff')
        city_id=data.get('city_id')
        packaging_cost = data.get('packaging_cost')
        total_amount = data.get('total_amount')
        status_id = data.get('status_id')

        # Вставляем данные в таблицу накладных
        cur.execute('''
            INSERT INTO waybill (sending_date, marking, box_count, total_weight, volume, density, tariff,city_id,  packaging_cost, total_amount, status_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (sending_date, marking, box_count, total_weight, cub, density, tariff,city_id, packaging_cost, total_amount, status_id))

        conn.commit()
        
        return jsonify({'message': 'Накладная успешно добавлена'}), 201
    except Exception as e:
        logging.error(f'Ошибка при добавлении накладной: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/delete_waybillb/<int:waybill_id>', methods=['DELETE'])
@admin_login_required
def delete_waybillb(waybill_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Удаляем накладную по указанному ID
        cur.execute('DELETE FROM waybill WHERE id = %s', (waybill_id,))
        affected_rows = cur.rowcount  

        conn.commit()
        
        return jsonify({'message': f'{affected_rows} накладных удалено'}), 200
    except Exception as e:
        logging.error(f'Ошибка при удалении накладной: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/get_all_waybillsb', methods=['GET'])
@admin_login_required
def get_all_waybillsb():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Получаем все накладные с названиями города и статуса
        query = '''
            SELECT w.id, w.sending_date, w.marking, w.box_count, 
                   w.total_weight, w.volume, w.density, w.tariff, 
                   c.name AS city_name, w.packaging_cost, w.total_amount, 
                   os.name AS status_name
            FROM waybill w
            JOIN city c ON w.city_id = c.id
            JOIN order_status os ON w.status_id = os.id
        '''
        cur.execute(query)
        waybills = cur.fetchall()

        # Преобразуем результат в список словарей для удобного вывода
        waybill_list = []
        for waybill in waybills:
            waybill_dict = {
                'id': waybill[0],
                'sending_date': waybill[1],
                'marking': waybill[2],
                'box_count': waybill[3],
                'total_weight': waybill[4],
                'volume': waybill[5],
                'density': waybill[6],
                'tariff': waybill[7],
                'city_name': waybill[8],
                'packaging_cost': waybill[9],
                'total_amount': waybill[10],
                'status_name': waybill[11]
            }
            waybill_list.append(waybill_dict)

        return jsonify(waybill_list), 200
    except Exception as e:
        logging.error(f'Ошибка при получении накладных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/change_waybillb_status/<int:waybill_id>', methods=['PUT'])
@admin_login_required
def change_waybill_statusb(waybill_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Проверяем, существует ли накладная с указанным идентификатором
        cur.execute('SELECT * FROM waybill WHERE id = %s', (waybill_id,))
        waybill = cur.fetchone()
        if not waybill:
            return jsonify({'error': 'Накладная с указанным идентификатором не найдена'}), 404

        # Изменяем статус накладной на 4 (доставлено)
        cur.execute('UPDATE waybill SET status_id = 4 WHERE id = %s', (waybill_id,))
        conn.commit()

        return jsonify({'success': 'Статус накладной успешно изменен на "Доставлено"'}), 200
    except Exception as e:
        logging.error(f'Ошибка при изменении статуса накладной: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/bishkek_bills')
@admin_login_required
def bishkek_bills():
    return render_template("bishkek_bill.html")

@app.route('/china_bills')
@admin_login_required
def china_bills():
    return render_template("chinabill.html")

@app.route('/sort_stat')
@admin_login_required
def stat_sort():
    return render_template("stat_sort.html")

@app.route('/cities')
@admin_login_required
def cities():
    return render_template("cities.html")

@app.route('/add_city', methods=['POST'])
@admin_login_required
def add_city():
    try:
        data = request.get_json()
        city_name = data.get('name')
        city_code = 'Random'
        description = 'Random description'  # Default description

        if not city_name:
            return jsonify({'error': 'City name is required'}), 400

        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('INSERT INTO city (name, city_code, description) VALUES (%s, %s, %s)',
                    (city_name, city_code, description))
        conn.commit()

        return jsonify({'message': 'City added successfully'}), 201
    except Exception as e:
        conn.rollback()  # Rollback the transaction on error
        logging.error(f'Error adding city: {e}')
        return jsonify({'error': 'Failed to add city'}), 500
    finally:
        cur.close()
        conn.close()

import logging

@app.route('/calculate_shipments_by_date', methods=['GET'])
@admin_login_required
def calculate_shipments_by_date():
    try:
        city_id = request.args.get('city_id')
        if not city_id:
            return jsonify({'error': 'City ID is required'}), 400

        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                sort_date::date AS shipment_date,
                COUNT(*) AS total_shipments,
                SUM(massa) AS total_weight,
                SUM(amount) AS total_amount
            FROM
                "Order"
            WHERE
                city_id = %s
            GROUP BY
                sort_date::date
            ORDER BY
                sort_date::date
        """, (city_id,))

        rows = cur.fetchall()
        result = []
        for row in rows:
            shipment_date = row[0].strftime('%Y-%m-%d') if row[0] is not None else None
            result.append({
                'shipment_date': shipment_date,
                'total_shipments': row[1],
                'total_weight': float(row[2]) if row[2] else None,
                'total_amount': float(row[3]) if row[3] else None
            })

        logging.info(f'Shipments calculation successful for city_id={city_id}')
        return jsonify(result)
    except Exception as e:
        logging.error(f'Error calculating shipments: {e}')
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/calculate_shipments_last_3_months', methods=['GET'])
@admin_login_required
def calculate_shipments_last_3_months():
    try:
        city_id = request.args.get('city_id')
        if not city_id:
            return jsonify({'error': 'City ID is required'}), 400

        conn = get_database_connection()
        cur = conn.cursor()

        # Получение текущей даты
        current_date = datetime.now().date()
        # Вычисление начальной даты (три месяца назад)
        start_date = current_date - timedelta(days=90)

        cur.execute("""
            SELECT
                TO_CHAR(sort_date, 'YYYY-MM') AS month,
                COUNT(*) AS total_shipments,
                SUM(massa) AS total_weight,
                SUM(amount) AS total_amount
            FROM
                "Order"
            WHERE
                city_id = %s
                AND sort_date >= %s
            GROUP BY
                TO_CHAR(sort_date, 'YYYY-MM')
            ORDER BY
                TO_CHAR(sort_date, 'YYYY-MM')
        """, (city_id, start_date))

        rows = cur.fetchall()
        result = []
        for row in rows:
            result.append({
                'month': row[0],
                'total_shipments': row[1],
                'total_weight': float(row[2]) if row[2] else None,
                'total_amount': float(row[3]) if row[3] else None
            })
        
        logging.info(f'Shipments calculation for the last 3 months successful for city_id={city_id}')
        print("result", result)
        return jsonify(result)
    except Exception as e:
        logging.error(f'Error calculating shipments for the last 3 months: {e}')
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# def create_user_in_database(name, surname, city_id, phone_num, extra_phone_num, tg_nickname, email):
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     password = secrets.token_urlsafe(8)
#     login = f"user_{secrets.randbelow(1000)}"

#     cursor.execute("""
#         INSERT INTO "User" (name, surname, city_id, login, password)
#         VALUES (%s, %s, %s, %s, %s)
#         RETURNING id
#     """, (name, surname, city_id, login, password))

#     user_id = cursor.fetchone()[0]

#     cursor.execute("""
#         INSERT INTO Contact (phone_num, extra_phone_num, tg_nickname, email, user_id)
#         VALUES (%s, %s, %s, %s, %s)
#     """, (phone_num, extra_phone_num, tg_nickname, email, user_id))

#     connection.commit()
#     cursor.close()
#     connection.close()


# def search_user_by_name(search_query):
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     try:
#         cursor.execute("""
#             SELECT u.id AS user_id, u.name, u.surname, city.name AS city_name,
#                    c.id AS contact_id, c.phone_num, c.extra_phone_num, c.tg_nickname, c.email
#             FROM "User" u
#             LEFT JOIN Contact c ON u.id = c.user_id
#             LEFT JOIN City ON u.city_id = city.id
#             WHERE u.name ILIKE %s OR u.surname ILIKE %s
#         """, ('%' + search_query + '%', '%' + search_query + '%'))

#         rows = cursor.fetchall()

#         columns = ["user_id", "name", "surname", "city_name", "contact_id", "phone_num", "extra_phone_num", "tg_nickname", "email"]
#         df = pd.DataFrame(rows, columns=columns)

#         return df

#     except Exception as e:
#         print(f"Error: {e}")
#         return pd.DataFrame()

#     finally:
#         cursor.close()
#         connection.close()

# def fetch_user_by_id(user_id):
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     try:
#         cursor.execute("""
#             SELECT u.id AS user_id, u.name, u.surname, city.name AS city_name,
#                    c.id AS contact_id, c.phone_num, c.extra_phone_num, c.tg_nickname, c.email
#             FROM "User" u
#             LEFT JOIN Contact c ON u.id = c.user_id
#             LEFT JOIN City ON u.city_id = city.id
#             WHERE u.id = %s
#         """, (user_id,))

#         rows = cursor.fetchall()

#         columns = ["user_id", "name", "surname", "city_name", "contact_id", "phone_num", "extra_phone_num", "tg_nickname", "email"]
#         df = pd.DataFrame(rows, columns=columns)

#         return df.iloc[0] if not df.empty else pd.DataFrame()

#     except Exception as e:
#         print(f"Error: {e}")
#         return pd.DataFrame()

#     finally:
#         cursor.close()
#         connection.close()

# def update_user_data(user_id, new_name, new_surname):
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     try:
#         cursor.execute("""
#             UPDATE "User"
#             SET name = %s, surname = %s
#             WHERE id = %s
#         """, (new_name, new_surname, user_id))

#         connection.commit()


#     except Exception as e:
#         print(f"Error: {e}")
#         connection.rollback()

#     finally:
#         cursor.close()
#         connection.close()


# @app.route('/admin/search_user', methods=['GET', 'POST'])
# def search_user():
#     if request.method == 'POST':
#         search_query = request.form.get('search_query')
#         users = search_user_by_name(search_query)
#         return render_template('admin#order-payment.html', users=users)

   

# @app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
# def edit_user(user_id):
#     user_data = fetch_user_by_id(user_id)

#     if request.method == 'POST':
#         new_name = request.form.get('new_name')
#         new_surname = request.form.get('new_surname')
#         update_user_data(user_id, new_name, new_surname)
#         return redirect(url_for('user_management'))

#     return render_template('edit_user.html', user_data=user_data)

# @app.route('/create_user_form', methods=['GET'])
# def create_user_form():
#     cities = get_cities()
#     return render_template('create_user_form.html', cities=cities)

# @app.route('/create_user', methods=['POST'])
# def create_user():
#     name = request.form.get('name')
#     surname = request.form.get('surname')
#     city_id = request.form.get('city_id')
#     phone_num = request.form.get('phone_num')
#     extra_phone_num = request.form.get('extra_phone_num')
#     tg_nickname = request.form.get('tg_nickname')
#     email = request.form.get('email')

#     create_user_in_database(name, surname, city_id, phone_num, extra_phone_num, tg_nickname, email)

#     users_data = get_users_data()

#     return render_template('users_table.html', users_data=users_data)

# def get_cities():
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     cursor.execute("SELECT id, name FROM City")
#     cities = cursor.fetchall()

#     cursor.close()
#     connection.close()

#     return cities

# def get_users_data():
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     cursor.execute("""
#         SELECT u.id, u.name, u.surname, u.login, u.password, c.phone_num, c.extra_phone_num, c.tg_nickname, c.email
#         FROM "User" u
#         LEFT JOIN Contact c ON u.id = c.user_id
#     """)
    
#     data = cursor.fetchall()

#     cursor.close()
#     connection.close()

#     return data


# def upload_data_to_db(file_path):
#     try:
#         connection = get_database_connection()
#         cursor = connection.cursor()

#         df = pd.read_excel(file_path)

#         selected_columns = ['data_send_from_china', 'user_id', 'track_code', 'order_status_id']
#         df = df[selected_columns]

#         buffer = StringIO()
#         df.to_csv(buffer, index=False, header=False, sep='\t')
#         buffer.seek(0)

#         cursor.copy_expert("COPY \"Order\" (data_send_from_china, user_id, track_code, order_status_id) FROM STDIN WITH CSV HEADER DELIMITER '\t'", buffer)

#         connection.commit()
#         print("Data successfully uploaded to the 'Order' table.")
#     except Exception as e:
#         print(f"Error during data upload: {e}")


# def get_order_data():
#     try:
#         connection = get_database_connection()
#         cursor = connection.cursor()

#         cursor.execute("SELECT * FROM \"Order\"")
#         data = cursor.fetchall()

        
#         print(f"Retrieved data from the 'Order' table: {data}")
#         return data
#     except Exception as e:
#         print(f"Error during data retrieval: {e}")
    

#     finally:
#         if cursor:
#             cursor.close()
#         if connection:
#             connection.close()

# def allowed_file(filename):
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# @app.route('/admin/upload', methods=['GET', 'POST'])
# def upload_file():
#     if request.method == 'POST':
#         file = request.files['file']
#         if file and allowed_file(file.filename):
#             filename = secure_filename(file.filename)
#             file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#             file.save(file_path)

#             upload_data_to_db(file_path)

#             order_data = get_order_data()

#             return render_template('order_table.html', order_data=order_data)

#     return render_template('admin.html')





# def fetch_user_and_contacts_data():
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     try:
#         cursor.execute("""
#             SELECT u.id AS user_id, u.name, u.surname, city.name AS city_name,
#                    c.id AS contact_id, c.phone_num, c.extra_phone_num, c.tg_nickname, c.email
#             FROM "User" u
#             LEFT JOIN Contact c ON u.id = c.user_id
#             LEFT JOIN City ON u.city_id = city.id
#         """)

#         rows = cursor.fetchall()

#         columns = ["user_id", "name", "surname", "city_name", "contact_id", "phone_num", "extra_phone_num", "tg_nickname", "email"]
#         df = pd.DataFrame(rows, columns=columns)

#         return df

#     except Exception as e:
#         print(f"Error: {e}")
#         return pd.DataFrame()  

#     finally:
#         cursor.close()
#         connection.close()

# import openpyxl
# from openpyxl.utils.dataframe import dataframe_to_rows

# def create_excel_file(data):
#     wb = openpyxl.Workbook()
#     ws = wb.active

#     for row in dataframe_to_rows(data, index=False, header=True):
#         ws.append(row)

#     output = BytesIO()
#     wb.save(output)
#     output.seek(0)
    
#     return output

# @app.route('/admin/download_excel')
# def download_excel():
#     users = fetch_user_and_contacts_data()
#     excel_data = create_excel_file(users)
#     return send_file(excel_data, download_name='user_and_contacts_data.xlsx', as_attachment=True)


# # @app.route('/')
# # def index():
# #     data = fetch_user_and_contacts_data()
# #     return render_template('index.html', data=data)

# # @app.route('/download_excel')
# # def download_excel():
# #     data = fetch_user_and_contacts_data()
# #     excel_data = create_excel_file(data)
# #     return send_file(excel_data, download_name='user_and_contacts_data.xlsx', as_attachment=True)


# # @app.route('/admin1')
# # def admin_page():
# #     return render_template('admin1.html')


# # @app.route('/admin')
# # def admin():
# #     data = fetch_user_and_contacts_data()
# #     return render_template('admin.html', users=data)




# @app.route('/tables')
# def list_tables():
#     try:
#         with get_database_connection() as connection, connection.cursor() as cursor:
#             cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
#             tables = cursor.fetchall()

#         table_names = [table[0] for table in tables]

#         return render_template('tables.html', tables=table_names)

#     except Exception as e:
#         return jsonify({'error': str(e)})

# if __name__ == '__main__':
#     app.run(debug=True)


if __name__ == '__main__':
    app.debug = True
    app.run()
