import os
import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from functools import wraps

from flask import Flask, render_template, request, jsonify, Response, session, redirect, url_for
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import requests

# pandas 是可选依赖，用于 WHO 数据下载
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None

load_dotenv()

app = Flask(__name__)

# ========== 配置 ==========
BIRTH_DATE = os.getenv('BIRTH_DATE', '2024-01-01')
SHEET_ID = os.getenv('SHEET_ID', '')
OWNER_EMAIL = os.getenv('OWNER_EMAIL', '')
APP_PASSWORD = os.getenv('APP_PASSWORD', 'family')
SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')

app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(days=30)

# 时区设置 - 尝试使用 zoneinfo，失败则使用 UTC+8 固定偏移
try:
    SINGAPORE_TZ = ZoneInfo('Asia/Singapore')
except Exception:
    # 如果时区数据不可用，使用 UTC+8 的固定偏移
    from datetime import timezone, timedelta
    SINGAPORE_TZ = timezone(timedelta(hours=8))

# ========== 工作表定义 ==========
SHEET_HEADERS = {
    'growth': ['date', 'weight_kg', 'height_cm', 'head_cm', 'note'],
    'milk': ['timestamp', 'amount_ml', 'type', 'note'],
    'food': ['timestamp', 'food_type', 'amount', 'note'],
    'poop': ['timestamp', 'type', 'color', 'note'],
    'sleep': ['start_time', 'end_time', 'duration_min', 'note'],
    'photo': ['timestamp', 'drive_url', 'caption'],
    'milestone': ['date', 'category', 'description'],
    'other': ['timestamp', 'category', 'content']
}

# ========== Google 认证 ==========
def get_service_account_creds():
    """获取 Service Account 凭证（用于 Sheets）"""
    service_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', '')
    if service_json:
        print(f'GOOGLE_SERVICE_ACCOUNT_JSON 长度: {len(service_json)}')
        try:
            info = json.loads(service_json)
            print('Service Account JSON 解析成功')
            return Credentials.from_service_account_info(
                info,
                scopes=['https://www.googleapis.com/auth/spreadsheets',
                        'https://www.googleapis.com/auth/drive']
            )
        except json.JSONDecodeError as e:
            print(f'Service Account JSON 解析错误: {e}')
            print(f'JSON 前100字符: {service_json[:100]}')
        except Exception as e:
            print(f'Service Account 凭证创建错误: {e}')
    else:
        print('GOOGLE_SERVICE_ACCOUNT_JSON 环境变量未设置')
    
    # 尝试本地文件
    if os.path.exists('service_account.json'):
        print('从本地文件 service_account.json 加载凭证')
        return Credentials.from_service_account_file(
            'service_account.json',
            scopes=['https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive']
        )
    
    print('无法获取 Service Account 凭证')
    return None


def get_oauth_creds():
    """获取 OAuth 凭证（用于上传照片到 Drive）"""
    client_id = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')
    client_secret = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')
    refresh_token = os.getenv('GOOGLE_OAUTH_REFRESH_TOKEN', '')
    
    if client_id and client_secret and refresh_token:
        creds = OAuthCredentials(
            None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri='https://oauth2.googleapis.com/token',
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        creds.refresh(Request())
        return creds
    return None


def get_sheets_client():
    """获取 Sheets 客户端"""
    creds = get_service_account_creds()
    if creds:
        return gspread.Client(auth=creds)
    return None


def get_drive_service():
    """获取 Drive 服务（仅用于 Sheets 元数据）"""
    creds = get_service_account_creds()
    if creds:
        return build('drive', 'v3', credentials=creds)
    return None


def get_drive_upload_service():
    """获取 Drive 上传服务（只用 OAuth，Service Account 无存储配额无法上传）"""
    try:
        creds = get_oauth_creds()
        if creds:
            return build('drive', 'v3', credentials=creds)
        raise Exception('未配置 OAuth 凭证（GOOGLE_OAUTH_CLIENT_ID / SECRET / REFRESH_TOKEN）')
    except Exception as e:
        raise Exception(f'Drive 上传需要有效的 OAuth token。请运行 get_refresh_token.py 重新生成: {e}')


def ensure_worksheet(sh, name, headers):
    """确保工作表存在，不存在则创建"""
    try:
        ws = sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=1000, cols=len(headers))
        ws.append_row(headers)
    return ws


# 全局缓存
_spreadsheet_cache = None
_cache_timestamp = 0
CACHE_TTL = 300  # 5分钟缓存（电子表格连接对象）

# 每个 Sheet 的数据缓存（内存，60秒 TTL）
_sheet_data_cache = {}   # { 'sheet_name': {'data': [...], 'ts': float} }
SHEET_DATA_TTL = 60      # 秒


def _get_sheet_records(sh, sheet_name):
    """获取 sheet 数据，优先返回内存缓存（60s TTL）"""
    global _sheet_data_cache
    now = time.time()
    entry = _sheet_data_cache.get(sheet_name)
    if entry and (now - entry['ts']) < SHEET_DATA_TTL:
        return entry['data']
    # 缓存未命中，从 Google 读取
    ws_name = 'Sheet1' if sheet_name == 'growth' else sheet_name
    try:
        ws = sh.worksheet(ws_name)
        records = ws.get_all_records()
    except Exception as e:
        print(f'读取 {sheet_name} 失败: {e}')
        records = []
    _sheet_data_cache[sheet_name] = {'data': records, 'ts': now}
    return records


def _invalidate_sheet_cache(sheet_name):
    """清除指定 sheet 的数据缓存"""
    _sheet_data_cache.pop(sheet_name, None)

def init_spreadsheet():
    """初始化电子表格结构（带缓存）"""
    global _spreadsheet_cache, _cache_timestamp
    
    # 检查缓存
    current_time = time.time()
    if _spreadsheet_cache and (current_time - _cache_timestamp) < CACHE_TTL:
        return _spreadsheet_cache
    
    client = get_sheets_client()
    if not client:
        print('错误: 无法创建 Sheets 客户端，请检查 GOOGLE_SERVICE_ACCOUNT_JSON')
        return None
    
    if not SHEET_ID:
        print('错误: SHEET_ID 未设置')
        return None
    
    try:
        print(f'正在连接 Google Sheet: {SHEET_ID}')
        sh = client.open_by_key(SHEET_ID)
        print('成功连接到 Google Sheet')
        
        # 确保 Sheet1 是成长记录表
        try:
            try:
                ws = sh.worksheet('Sheet1')
                first_row = ws.row_values(1)
                if not first_row:
                    ws.append_row(SHEET_HEADERS['growth'])
            except gspread.WorksheetNotFound:
                print('Sheet1 不存在，正在创建...')
                ws = sh.add_worksheet(title='Sheet1', rows=1000, cols=10)
                ws.append_row(SHEET_HEADERS['growth'])
        except Exception as e:
            print(f'Sheet1 检查错误: {e}')
        
        # 确保其他工作表存在
        for name, headers in SHEET_HEADERS.items():
            if name != 'growth':
                try:
                    ensure_worksheet(sh, name, headers)
                except Exception as e:
                    print(f'创建工作表 {name} 错误: {e}')
        
        # 更新缓存
        _spreadsheet_cache = sh
        _cache_timestamp = current_time
        
        return sh
    except Exception as e:
        print(f'初始化表格错误: {e}')
        import traceback
        traceback.print_exc()
        return None


# ========== 认证 ==========
def requires_auth(f):
    """检查 session，未登录则跳转登录页"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({'error': '未登录'}), 401
            return redirect(url_for('login_page', next=request.url))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        remember = request.form.get('remember') == '1'
        if password == APP_PASSWORD:
            session['logged_in'] = True
            session.permanent = remember   # remember=True 保孕30天, False关浏览器失效
            next_url = request.form.get('next') or url_for('index')
            return redirect(next_url)
        error = '密码错误，请重试'
    next_url = request.args.get('next', '')
    return render_template('login.html', error=error, next=next_url)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


# ========== WHO 数据 ==========
def download_who_data():
    """下载 WHO 成长参考数据"""
    data_dir = 'data/who'
    os.makedirs(data_dir, exist_ok=True)
    
    # 检查是否已有缓存数据
    try:
        cached_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
        if cached_files:
            return data_dir
    except:
        pass
    
    # 创建示例 WHO 数据文件（简化版）
    # 真实 WHO 数据需要从官网下载或使用 pandas 处理
    for metric in ['weight', 'height']:
        for gender in ['boys', 'girls']:
            file_path = f'{data_dir}/{metric}_{gender}.csv'
            if not os.path.exists(file_path):
                # 使用简化示例数据
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('month,p3,p15,p50,p85,p97\n')
                    for i in range(25):
                        # 示例数据，实际应使用真实 WHO 数据
                        if metric == 'weight':
                            base = 3.5 + i * 0.5  # 简化的体重增长
                        else:
                            base = 50 + i * 2.5   # 简化的身高增长
                        f.write(f'{i},{base*0.8},{base*0.9},{base},{base*1.1},{base*1.2}\n')
    
    return data_dir


def load_who_data(metric, gender, age_months):
    """加载指定月龄的 WHO 参考数据"""
    data_dir = download_who_data()
    file_path = f'{data_dir}/{metric}_{gender}.csv'
    
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        headers = lines[0].strip().split(',')
        target_month = int(age_months)
        
        for line in lines[1:]:
            values = line.strip().split(',')
            if int(values[0]) == target_month:
                return dict(zip(headers, [float(v) for v in values]))
    except Exception as e:
        print(f'加载 WHO 数据错误: {e}')
    
    return None


# ========== 工具函数 ==========
def get_today_str():
    """获取新加坡时区的今日日期字符串"""
    now = datetime.now(SINGAPORE_TZ)
    return f"{now.year}-{str(now.month).zfill(2)}-{str(now.day).zfill(2)}"


def get_now_str():
    """获取新加坡时区的当前时间字符串"""
    now = datetime.now(SINGAPORE_TZ)
    return now.strftime('%Y-%m-%d %H:%M')


def calculate_age_days():
    """计算宝宝出生至今的天数"""
    birth = datetime.strptime(BIRTH_DATE, '%Y-%m-%d').date()
    today = datetime.now(SINGAPORE_TZ).date()
    return (today - birth).days


def calculate_age_months():
    """计算宝宝月龄"""
    birth = datetime.strptime(BIRTH_DATE, '%Y-%m-%d').date()
    today = datetime.now(SINGAPORE_TZ).date()
    months = (today.year - birth.year) * 12 + today.month - birth.month
    if today.day < birth.day:
        months -= 1
    return max(0, months)


# ========== API 端点 ==========
@app.route('/')
@requires_auth
def index():
    """主页"""
    return render_template('index.html',
                         birth_date=BIRTH_DATE,
                         age_days=calculate_age_days(),
                         age_months=calculate_age_months())


@app.route('/api/data')
@requires_auth
def get_data():
    """获取所有数据（各 sheet 独立 60s 缓存）"""
    sh = init_spreadsheet()
    if not sh:
        return jsonify({'error': '无法连接到表格'}), 500
    
    result = {}
    for name in ['growth', 'milk', 'food', 'poop', 'sleep', 'photo', 'milestone', 'other']:
        result[name] = _get_sheet_records(sh, name)
    
    # 添加 WHO 参考数据（仅用于当前月龄）
    age_months = calculate_age_months()
    result['who'] = {
        'weight_boys': load_who_data('weight', 'boys', age_months),
        'weight_girls': load_who_data('weight', 'girls', age_months),
        'height_boys': load_who_data('height', 'boys', age_months),
        'height_girls': load_who_data('height', 'girls', age_months),
    }
    
    result['age_days'] = calculate_age_days()
    result['age_months'] = age_months
    result['today'] = get_today_str()
    
    return jsonify(result)


@app.route('/api/add', methods=['POST'])
@requires_auth
def add_record():
    """添加记录"""
    data = request.json
    record_type = data.get('type', '')
    
    sh = init_spreadsheet()
    if not sh:
        return jsonify({'error': '无法连接到表格'}), 500
    
    try:
        if record_type == 'growth':
            ws = sh.worksheet('Sheet1')
            row = [
                data.get('date', get_today_str()),
                data.get('weight_kg', ''),
                data.get('height_cm', ''),
                data.get('head_cm', ''),
                data.get('note', '')
            ]
        else:
            headers = SHEET_HEADERS.get(record_type)
            if not headers:
                return jsonify({'error': f'未知记录类型: {record_type}'}), 400
            
            ws = ensure_worksheet(sh, record_type, headers)
            
            # 根据类型构建行数据
            if record_type == 'milk':
                row = [
                    data.get('timestamp', get_now_str()),
                    data.get('amount_ml', ''),
                    data.get('milk_type', data.get('type', '')),
                    data.get('note', '')
                ]
            elif record_type == 'food':
                row = [
                    data.get('timestamp', get_now_str()),
                    data.get('food_type', ''),
                    data.get('amount', ''),
                    data.get('note', '')
                ]
            elif record_type == 'poop':
                row = [
                    data.get('timestamp', get_now_str()),
                    data.get('poop_type', data.get('type', '')),
                    data.get('color', ''),
                    data.get('note', '')
                ]
            elif record_type == 'sleep':
                row = [
                    data.get('start_time', ''),
                    data.get('end_time', ''),
                    data.get('duration_min', ''),
                    data.get('note', '')
                ]
            elif record_type == 'photo':
                row = [
                    data.get('timestamp', get_now_str()),
                    data.get('drive_url', ''),
                    data.get('caption', '')
                ]
            elif record_type == 'milestone':
                row = [
                    data.get('date', get_today_str()),
                    data.get('category', ''),
                    data.get('description', '')
                ]
            elif record_type == 'other':
                row = [
                    data.get('timestamp', get_now_str()),
                    data.get('category', ''),
                    data.get('content', '')
                ]
            else:
                row = []
        
        if row:
            ws.append_row(row)
            _invalidate_sheet_cache(record_type)  # 清除该 sheet 的缓存
            return jsonify({'success': True})
        
        return jsonify({'error': '无法构建记录'}), 400
        
    except Exception as e:
        print(f'添加记录错误: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/update', methods=['POST'])
@requires_auth
def update_record():
    """更新记录（删除旧行 + 追加新行）"""
    data = request.json
    record_type = data.get('type', '')
    row_idx = data.get('row_idx', 0)  # 行号（从1开始，0表示新增）
    
    if row_idx > 0:
        # 需要删除旧行
        sh = init_spreadsheet()
        if not sh:
            return jsonify({'error': '无法连接到表格'}), 500
        
        try:
            if record_type == 'growth':
                ws = sh.worksheet('Sheet1')
            else:
                headers = SHEET_HEADERS.get(record_type)
                if not headers:
                    return jsonify({'error': f'未知记录类型: {record_type}'}), 400
                ws = sh.worksheet(record_type)
            
            # 删除旧行（Google Sheets API 行号从1开始，但 row_values 第0行是表头，所以数据从第2行开始）
            # 这里假设 row_idx 已经是实际行号
            ws.delete_rows(row_idx)
        except Exception as e:
            print(f'删除旧行错误: {e}')
            return jsonify({'error': f'删除旧行失败: {e}'}), 500
    
    # 添加新记录
    return add_record()


@app.route('/api/delete', methods=['POST'])
@requires_auth
def delete_record():
    """删除记录"""
    data = request.json
    record_type = data.get('type', '')
    row_idx = data.get('row_idx', 0)
    
    if row_idx < 2:
        return jsonify({'error': '无效的行号'}), 400
    
    sh = init_spreadsheet()
    if not sh:
        return jsonify({'error': '无法连接到表格'}), 500
    
    try:
        if record_type == 'growth':
            ws = sh.worksheet('Sheet1')
        else:
            ws = sh.worksheet(record_type)
        
        ws.delete_rows(row_idx)
        _invalidate_sheet_cache(record_type)  # 清除该 sheet 的缓存

        # 如果提供了 Drive 文件 ID，同时删除 Drive 上的文件
        drive_file_id = data.get('drive_file_id', '')
        if drive_file_id:
            try:
                svc = get_drive_upload_service()
                svc.files().delete(fileId=drive_file_id).execute()
                print(f'Drive 文件 {drive_file_id} 已删除')
            except Exception as de:
                print(f'删除 Drive 文件失败 (非致命): {de}')

        return jsonify({'success': True})
        
    except Exception as e:
        print(f'删除记录错误: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload', methods=['POST'])
@requires_auth
def upload_photo():
    """上传照片到 Google Drive"""
    if 'photo' not in request.files:
        return jsonify({'error': '没有照片文件'}), 400
    
    file = request.files['photo']
    caption = request.form.get('caption', '')
    
    if file.filename == '':
        return jsonify({'error': '文件名不能为空'}), 400
    
    try:
        service = get_drive_upload_service()
    except Exception as e:
        print(f'上传照片错误: {e}')
        return jsonify({'error': str(e)}), 500
    
    try:
        # 创建文件元数据
        timestamp = datetime.now(SINGAPORE_TZ).strftime('%Y%m%d_%H%M%S')
        safe_filename = re.sub(r'[^\w\-.]', '_', file.filename)
        file_metadata = {
            'name': f'{timestamp}_{safe_filename}',
            'mimeType': file.content_type or 'image/jpeg'
        }
        
        # 上传文件
        from googleapiclient.http import MediaIoBaseUpload
        import io
        
        file_content = file.read()
        media = MediaIoBaseUpload(
            io.BytesIO(file_content),
            mimetype=file.content_type or 'image/jpeg',
            resumable=True
        )
        
        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        file_id = uploaded_file.get('id')
        web_link = uploaded_file.get('webViewLink', '')
        
        # 设置文件共享权限
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        direct_link = f'https://drive.google.com/uc?export=view&id={file_id}'
        
        # 注意：不再在此处保存记录到表格，由前端 submitPhoto/submitMilestone 调用 /api/add 统一处理
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'drive_url': direct_link,
            'web_link': web_link
        })
        
    except Exception as e:
        print(f'上传照片错误: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/who')
@requires_auth
def get_who_data():
    """获取 WHO 成长参考数据"""
    metric = request.args.get('metric', 'weight')
    gender = request.args.get('gender', 'boys')
    
    # 获取从 0 到当前月龄的所有数据
    age_months = calculate_age_months()
    data = []
    
    for month in range(0, age_months + 1):
        row = load_who_data(metric, gender, month)
        if row:
            data.append(row)
    
    return jsonify({'data': data, 'months': list(range(0, age_months + 1))})


@app.route('/api/stats')
@requires_auth
def get_stats():
    """获取今日统计"""
    sh = init_spreadsheet()
    if not sh:
        return jsonify({'error': '无法连接到表格'}), 500
    
    today = get_today_str()
    today_start = f'{today} 00:00'
    
    stats = {
        'milk_total': 0,
        'food_count': 0,
        'poop_count': 0,
        'sleep_total': 0,
        'photo_count': 0
    }
    
    try:
        # 统计今日喂奶量
        try:
            ws = sh.worksheet('milk')
            records = ws.get_all_records()
            for r in records:
                ts = str(r.get('timestamp', ''))
                if ts.startswith(today):
                    amount = r.get('amount_ml', 0)
                    if amount:
                        try:
                            stats['milk_total'] += int(amount)
                        except:
                            pass
        except:
            pass
        
        # 统计今日辅食
        try:
            ws = sh.worksheet('food')
            records = ws.get_all_records()
            for r in records:
                ts = str(r.get('timestamp', ''))
                if ts.startswith(today):
                    stats['food_count'] += 1
        except:
            pass
        
        # 统计今日排便
        try:
            ws = sh.worksheet('poop')
            records = ws.get_all_records()
            for r in records:
                ts = str(r.get('timestamp', ''))
                if ts.startswith(today):
                    stats['poop_count'] += 1
        except:
            pass
        
        # 统计今日睡眠
        try:
            ws = sh.worksheet('sleep')
            records = ws.get_all_records()
            for r in records:
                start = str(r.get('start_time', ''))
                if start.startswith(today):
                    duration = r.get('duration_min', 0)
                    if duration:
                        try:
                            stats['sleep_total'] += int(duration)
                        except:
                            pass
        except:
            pass
        
        # 统计今日照片
        try:
            ws = sh.worksheet('photo')
            records = ws.get_all_records()
            for r in records:
                ts = str(r.get('timestamp', ''))
                if ts.startswith(today):
                    stats['photo_count'] += 1
        except:
            pass
        
    except Exception as e:
        print(f'获取统计错误: {e}')
    
    return jsonify(stats)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
