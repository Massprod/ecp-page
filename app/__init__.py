import os
import base64
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from urllib.parse import quote
from requests import request as out_req, ConnectionError
from flask import Flask, render_template, request as inc_req


app = Flask(__name__)

load_dotenv('.env')

#region Logs
log_dir: str = os.getenv('LOG_DIR', './logs')
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, 'app_logs.log')
# ✅ Create rotating handler: max 5MB per file, keep 5 backups
rotating_handler = RotatingFileHandler(
    log_file_path,
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=5,
    encoding='utf-8'
)

formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
rotating_handler.setFormatter(formatter)

# ✅ Apply to root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(rotating_handler)

# ✅ Apply also to Flask's app.logger
app.logger.setLevel(logging.INFO)
app.logger.addHandler(rotating_handler)


@app.before_request
def log_request_info():
    app.logger.info(f'Request: {inc_req.method} {inc_req.url}')
    app.logger.info(f'Headers: {inc_req.headers}')
    app.logger.info(f'Body: {inc_req.get_data()}')


@app.after_request
def log_response_info(response):
    app.logger.info(f'Response status: {response.status}')
    app.logger.info(f'Response headers: {response.headers}')
    return response
#endregion Logs

#region ServiceCon
req_api_dom: str = os.getenv('API_DOM')
req_api_name: str = os.getenv('API_NAME')
req_base_url: str = f'{req_api_dom}/{req_api_name}'

service_login: str = os.getenv('SYS_LOGIN')
service_pass: str = os.getenv('SYS_PASS')

app.logger.info(f'ENV_SETUP\n' \
                f'API_DOM = {req_api_dom}\n' \
                f'API_NAME = {req_api_name}\n' \
                f'LOGIN = {service_login}\n' \
                f'PASS = {service_pass}\n' \
                f'BASE_URL = {req_base_url}')

service_auth_string: str = f'{service_login}:{service_pass}'
service_auth_string_bytes: bytes = service_auth_string.encode('utf-8')
service_auth_string_base64: str = base64.b64encode(service_auth_string_bytes).decode('utf-8')
#endregion ServiceCon

basic_headers: dict[str, str] = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'en',
    'Authorization': f'Basic {service_auth_string_base64}',
    'Cache-Control': 'max-age=0',
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    'Host': 'localhost',
    'Sec-Ch-Ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Microsoft Edge";v="126"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0'
}


class CustomError(Exception):
    def __init__(self, status_code, message, lang, error_code):
        self.status_code = status_code
        self.message = message
        self.lang = lang
        self.error_code = error_code


def get_user_language():
    lang = inc_req.headers.get('Accept-Language', 'en').split(',')[0]
    return lang


def get_error_messages(error_code, lang):
    messages = {
        400: {
            'en': 'Invalid or missing query parameters: `type` and `ref` are required.',
            'ru': 'Некорректные или отсутствующие параметры запроса: `type` и `ref` обязательны.',
        },
        404: {
            'en': 'Document not found',
            'ru': 'Документ не найден',
        },
        409: {
            'en': 'Document not signed',
            'ru': 'Документ не подписан',
        },
        500: {
            'en': 'Service is unavailable',
            'ru': 'Сервис недоступен'
        }
    }
    if error_code not in messages:
        return messages[500].get(lang, 'en')
    return messages[error_code].get(lang, 'en')


@app.route('/', methods=['GET'])
def get_doc():
    status_code: int = 200
    doc_type = inc_req.args.get('type')
    ref_type = inc_req.args.get('ref')
    preferred_language = get_user_language()[:2]
    if not doc_type or not ref_type:
        status_code = 400
        message = get_error_messages(status_code, preferred_language)
        raise CustomError(status_code, message, preferred_language, status_code)
    cor_doc_type = quote(doc_type)
    cor_ref_type = quote(ref_type)
    full_req_url = f'{req_base_url}?type={cor_doc_type}&ref={cor_ref_type}'
    app.logger.error(f'REQUEST_URL = {full_req_url}')
    try:
        request = out_req('GET', full_req_url, headers=basic_headers, verify=False)
    except ConnectionError as error:
        app.logger.error('Connection error', exc_info=True)
        status_code = 500
        message = get_error_messages(status_code, preferred_language)
        raise CustomError(status_code, message, preferred_language, status_code)
    if 200 != request.status_code:
        status_code = request.status_code
        message = get_error_messages(status_code, preferred_language)
        raise CustomError(status_code, message, preferred_language, status_code)
    request_data = request.json()
    app.logger.info(f"RESPONSE_DATA: {request_data}")
    for key, value in request_data.items():
        print(key, value)
    data = {}
    # Если не основных данных о документе => значит он был не найден. Что изначально 404.
    document_data = {
        'document_name': request_data['ДанныеДокумента']['Наименование'],
        'document_number': request_data['ДанныеДокумента']['НомерДокумента'],
        'registration_date': request_data['ДанныеДокумента']['ДатаРегистрации'],
        'registered_by': request_data['ДанныеДокумента']['Зарегистрировал'],
        'prepared_by': request_data['ДанныеДокумента'].get('Подготовил', ''),
    }
    # Если не будет какого-либо из пунктов, мы можем отрендерить пустую страницу.
    # Поэтому добавляю эти кринж проверки.
    data['document_data'] = document_data
    if 'ДанныеПодписи' in request_data:
        open_key: str = request_data['ДанныеПодписи']['ОткрытыйКлюч']
        sign_data = {
            "signed_by": request_data['ДанныеПодписи']["УстановившийПодпись"],
            "sign_date": request_data["ДанныеПодписи"]["ДатаПодписи"],
            "start_time": request_data['ДанныеПодписи']["ДатаНачала"],
            "end_time": request_data['ДанныеПодписи']['ДатаОкончания'],
            "provider": request_data['ДанныеПодписи']['КемВыдан'],
            "receiver": request_data['ДанныеПодписи']['КомуВыдан'],
            "open_key": open_key,
        }
        data['sign_data'] = sign_data
    if 'ДанныеФайлов' in request_data:
        data['attached_files'] = {}
        for file, file_data in request_data['ДанныеФайлов'].items():
            cor_file_data = {
                'name': file_data['ПрикреплённыйФайл'],
                'sign_date': file_data['ДатаПодписи'],
                'signed_by': file_data['УстановившийПодпись'],
                'attached_by': file_data['ПрикрепившийФайл'],
            }
            data['attached_files'][file] = cor_file_data
    if 'ДанныеВизСогласования' in request_data:
        data['approvement_data'] = {}
        for index, person in enumerate(request_data['ДанныеВизСогласования']):
            data['approvement_data'][index] = {
                "role": person["Должность"],
                "name": person["Исполнитель"],
                "sign_date": person["ДатаИсполнения"],
                "approvement_mark": person["РезультатСогласования"],
                "comment": person["РезультатВыполнения"],
            }
    if 'ДанныеQR' in request_data:
        data['qr_data'] = {
            'qr_binary': request_data['ДанныеQR']['ДвоичныеДанныеQRКода'],
            'qr_link': request_data['ДанныеQR']['ОригиналСсылки'],
        }
    return render_template('main_page.html', **data), status_code


@app.errorhandler(CustomError)
def handle_custom_error(error):
    app.logger.error(f'Error: {error.message} (Code: {error.error_code})', exc_info=True)
    response = render_template(
        'error_page.html',
        message=error.message,
        lang=error.lang,
        error_code=error.error_code,
    )
    return response, error.status_code
