import asyncio
import base64
import json
import mimetypes
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from queue import Queue
from flask_cors import CORS
from myUtils.auth import check_cookie
from flask import Flask, request, jsonify, Response, render_template, send_from_directory
from werkzeug.utils import secure_filename
from conf import BASE_DIR
from myUtils.login import get_tencent_cookie, douyin_cookie_gen, get_ks_cookie, xiaohongshu_cookie_gen
from myUtils.postVideo import post_video_tencent, post_video_DouYin, post_video_ks, post_video_xhs

active_queues = {}
publish_tasks = {}
publish_tasks_lock = threading.Lock()
app = Flask(__name__)
DEFAULT_PUBLISH_TASK_TIMEOUT_SECONDS = 30 * 60

#允许所有来源跨域访问
CORS(app)

# 限制上传文件大小为160MB
app.config['MAX_CONTENT_LENGTH'] = 160 * 1024 * 1024

# 获取当前目录（假设 index.html 和 assets 在这里）
current_dir = os.path.dirname(os.path.abspath(__file__))

# 处理所有静态资源请求（未来打包用）
@app.route('/assets/<filename>')
def custom_static(filename):
    return send_from_directory(os.path.join(current_dir, 'assets'), filename)

# 处理 favicon.ico 静态资源（未来打包用）
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(current_dir, 'assets'), 'vite.svg')

@app.route('/vite.svg')
def vite_svg():
    return send_from_directory(os.path.join(current_dir, 'assets'), 'vite.svg')

# （未来打包用）
@app.route('/')
def index():  # put application's code here
    return send_from_directory(current_dir, 'index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No file part in the request"
        }), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No selected file"
        }), 400
    try:
        # 保存文件到指定位置
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        safe_name = secure_filename(file.filename)
        if not safe_name:
            return jsonify({"code": 400, "data": None, "msg": "Invalid filename"}), 400
        filepath = Path(BASE_DIR / "videoFile" / f"{uuid_v1}_{safe_name}")
        file.save(filepath)
        return jsonify({"code":200,"msg": "File uploaded successfully", "data": f"{uuid_v1}_{safe_name}"}), 200
    except Exception as e:
        return jsonify({"code":500,"msg": str(e),"data":None}), 500

@app.route('/getFile', methods=['GET'])
def get_file():
    # 获取 filename 参数
    filename = request.args.get('filename')

    if not filename:
        return jsonify({"code": 400, "msg": "filename is required", "data": None}), 400

    # 防止路径穿越攻击
    if '..' in filename or filename.startswith('/'):
        return jsonify({"code": 400, "msg": "Invalid filename", "data": None}), 400

    # 拼接完整路径
    file_path = str(Path(BASE_DIR / "videoFile"))

    # 返回文件
    return send_from_directory(file_path,filename)


@app.route('/uploadSave', methods=['POST'])
def upload_save():
    if 'file' not in request.files:
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No file part in the request"
        }), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No selected file"
        }), 400

    # 获取表单中的自定义文件名（可选）
    custom_filename = request.form.get('filename', None)
    if custom_filename:
        filename = secure_filename(custom_filename + "." + file.filename.split('.')[-1])
    else:
        filename = secure_filename(file.filename)
    if not filename:
        return jsonify({"code": 400, "data": None, "msg": "Invalid filename"}), 400

    try:
        # 生成 UUID v1
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")

        # 构造文件名和路径
        final_filename = f"{uuid_v1}_{filename}"
        filepath = Path(BASE_DIR / "videoFile" / f"{uuid_v1}_{filename}")

        # 保存文件
        file.save(filepath)

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO file_records (filename, filesize, file_path)
            VALUES (?, ?, ?)
                                ''', (filename, round(float(os.path.getsize(filepath)) / (1024 * 1024),2), final_filename))
            conn.commit()
            print("✅ 上传文件已记录")

        return jsonify({
            "code": 200,
            "msg": "File uploaded and saved successfully",
            "data": {
                "filename": filename,
                "filepath": final_filename
            }
        }), 200

    except Exception as e:
        print(f"Upload failed: {e}")
        return jsonify({
            "code": 500,
            "msg": f"upload failed: {e}",
            "data": None
        }), 500

@app.route('/getFiles', methods=['GET'])
def get_all_files():
    try:
        # 使用 with 自动管理数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row  # 允许通过列名访问结果
            cursor = conn.cursor()

            # 查询所有记录
            cursor.execute("SELECT * FROM file_records")
            rows = cursor.fetchall()

            # 将结果转为字典列表，并提取UUID
            data = []
            for row in rows:
                row_dict = dict(row)
                # 从 file_path 中提取 UUID (文件名的第一部分，下划线前)
                if row_dict.get('file_path'):
                    file_path_parts = row_dict['file_path'].split('_', 1)  # 只分割第一个下划线
                    if len(file_path_parts) > 0:
                        row_dict['uuid'] = file_path_parts[0]  # UUID 部分
                    else:
                        row_dict['uuid'] = ''
                else:
                    row_dict['uuid'] = ''
                data.append(row_dict)

            return jsonify({
                "code": 200,
                "msg": "success",
                "data": data
            }), 200
    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("get file failed!"),
            "data": None
        }), 500


@app.route("/getAccounts", methods=['GET'])
def getAccounts():
    """快速获取所有账号信息，不进行cookie验证"""
    try:
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
            SELECT * FROM user_info''')
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

            print("\n📋 当前数据表内容（快速获取）：")
            for row in rows:
                print(row)

            return jsonify(
                {
                    "code": 200,
                    "msg": None,
                    "data": rows_list
                }), 200
    except Exception as e:
        print(f"获取账号列表时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"获取账号列表失败: {str(e)}",
            "data": None
        }), 500


@app.route("/getValidAccounts",methods=['GET'])
async def getValidAccounts():
    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT * FROM user_info''')
        rows = cursor.fetchall()
        rows_list = [list(row) for row in rows]
        print("\n📋 当前数据表内容：")
        for row in rows:
            print(row)
        for row in rows_list:
            flag = await check_cookie(row[1],row[2])
            if not flag:
                row[4] = 0
                cursor.execute('''
                UPDATE user_info 
                SET status = ? 
                WHERE id = ?
                ''', (0,row[0]))
                conn.commit()
                print("✅ 用户状态已更新")
        for row in rows:
            print(row)
        return jsonify(
                        {
                            "code": 200,
                            "msg": None,
                            "data": rows_list
                        }),200


@app.route("/api/platforms", methods=["GET"])
def api_platforms():
    return jsonify([
        {"key": "douyin", "name": "抖音", "supportsVideo": True, "supportsImageText": True, "supportsSchedule": True},
        {"key": "xiaohongshu", "name": "小红书", "supportsVideo": True, "supportsImageText": True, "supportsSchedule": True},
        {"key": "kuaishou", "name": "快手", "supportsVideo": True, "supportsImageText": True, "supportsSchedule": True},
        {"key": "wechat_channels", "name": "视频号", "supportsVideo": True, "supportsImageText": False, "supportsSchedule": True},
        {"key": "bilibili", "name": "Bilibili", "supportsVideo": True, "supportsImageText": False, "supportsSchedule": True},
        {"key": "youtube", "name": "YouTube", "supportsVideo": True, "supportsImageText": False, "supportsSchedule": False},
    ])


@app.route("/api/accounts", methods=["GET"])
def api_accounts():
    accounts = []
    for platform in ("douyin", "xiaohongshu", "kuaishou", "tencent", "bilibili", "youtube"):
        accounts.extend(_list_cli_accounts(platform))
    legacy_accounts = _list_legacy_accounts()
    existing_keys = {(item["platform"], item["name"]) for item in accounts}
    for account in legacy_accounts:
        key = (account["platform"], account["name"])
        if key not in existing_keys:
            accounts.append(account)
    return jsonify(accounts)


@app.route("/api/accounts/<platform>", methods=["DELETE"])
def api_delete_account(platform):
    account_name = request.args.get("accountName") or request.args.get("account") or request.args.get("id")
    if not account_name:
        return jsonify({"detail": "accountName is required"}), 400

    normalized_platform = _normalize_platform(platform)
    if normalized_platform not in {"douyin", "xiaohongshu", "kuaishou", "tencent", "bilibili", "youtube"}:
        return jsonify({"detail": f"unsupported platform: {platform}"}), 400

    deleted_files = []
    deleted_legacy_rows = 0
    account_path = _account_file(normalized_platform, account_name)
    if account_path.exists():
        account_path.unlink()
        deleted_files.append(str(account_path))

    deleted_legacy_rows = _delete_legacy_account(_frontend_platform(normalized_platform), account_name)
    if not deleted_files and not deleted_legacy_rows:
        return jsonify({"detail": "account not found"}), 404

    return jsonify({
        "deleted": True,
        "accountName": account_name,
        "platform": _frontend_platform(normalized_platform),
        "deletedFiles": deleted_files,
        "deletedLegacyRows": deleted_legacy_rows,
    })


@app.route("/api/accounts/<platform>/login")
def api_account_login(platform):
    account_name = request.args.get("accountName") or request.args.get("account") or request.args.get("id")
    if not account_name:
        return jsonify({"detail": "accountName is required"}), 400

    normalized_platform = _normalize_platform(platform)
    if normalized_platform not in {"douyin", "xiaohongshu", "kuaishou", "tencent", "bilibili", "youtube"}:
        return jsonify({"detail": f"unsupported platform: {platform}"}), 400

    def stream():
        yield _sse({"type": "status", "message": f"正在启动 {normalized_platform} 登录子进程"})
        command = _sau_command([normalized_platform, "login", "--account", account_name, "--headed"])
        if normalized_platform == "bilibili":
            command = _sau_command([normalized_platform, "login", "--account", account_name])
        print(f"🚀 启动登录子进程: {' '.join(command)}", flush=True)
        yield from _stream_process(command, normalized_platform, account_name, expect_qrcode=True)

    response = Response(stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.route("/api/tasks", methods=["GET"])
def api_tasks():
    with publish_tasks_lock:
        tasks = sorted(publish_tasks.values(), key=lambda item: item["createdAt"], reverse=True)
    return jsonify(tasks)


@app.route("/api/publish/video", methods=["POST"])
def api_publish_video():
    payload = request.get_json() or {}
    platform = _normalize_platform(payload.get("platform", ""))
    if platform not in {"douyin", "xiaohongshu", "kuaishou", "tencent", "bilibili", "youtube"}:
        return jsonify({"detail": f"unsupported platform: {payload.get('platform')}"}), 400

    file_paths = payload.get("filePaths") or []
    account_ids = payload.get("accountIds") or []
    title = (payload.get("title") or "").strip()
    if not file_paths:
        return jsonify({"detail": "filePaths is required"}), 400
    if not account_ids:
        return jsonify({"detail": "accountIds is required"}), 400
    if not title:
        return jsonify({"detail": "title is required"}), 400

    account_names = [_account_name_from_id(account_id) for account_id in account_ids]
    task_id = str(uuid.uuid4())
    task = {
        "id": task_id,
        "title": title,
        "platform": _frontend_platform(platform),
        "accountNames": account_names,
        "status": "pending",
        "message": "发布任务已创建，等待子进程执行",
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "logs": [],
    }
    with publish_tasks_lock:
        publish_tasks[task_id] = task

    thread = threading.Thread(target=_run_publish_task, args=(task_id, platform, payload, account_names), daemon=True)
    thread.start()
    return jsonify({key: value for key, value in task.items() if key != "logs"}), 200


@app.route("/api/publish/note", methods=["POST"])
def api_publish_note():
    payload = request.get_json() or {}
    platform = _normalize_platform(payload.get("platform", ""))
    if platform not in {"douyin", "xiaohongshu", "kuaishou"}:
        return jsonify({"detail": f"platform does not support image-text publishing: {payload.get('platform')}"}), 400
    image_paths = payload.get("imagePaths") or payload.get("filePaths") or []
    account_ids = payload.get("accountIds") or []
    title = (payload.get("title") or "").strip()
    content = (payload.get("content") or payload.get("description") or "").strip()
    if not image_paths:
        return jsonify({"detail": "imagePaths is required"}), 400
    if not account_ids:
        return jsonify({"detail": "accountIds is required"}), 400
    if not title or not content:
        return jsonify({"detail": "title and content are required"}), 400

    account_names = [_account_name_from_id(account_id) for account_id in account_ids]
    task_id = str(uuid.uuid4())
    task = {
        "id": task_id,
        "title": title,
        "platform": _frontend_platform(platform),
        "accountNames": account_names,
        "status": "pending",
        "message": "图文发布任务已创建，等待子进程执行",
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "logs": [],
    }
    payload = {**payload, "contentType": "note", "imagePaths": image_paths, "description": content}
    with publish_tasks_lock:
        publish_tasks[task_id] = task
    thread = threading.Thread(target=_run_publish_task, args=(task_id, platform, payload, account_names), daemon=True)
    thread.start()
    return jsonify({key: value for key, value in task.items() if key != "logs"}), 200

@app.route('/deleteFile', methods=['GET'])
def delete_file():
    file_id = request.args.get('id')

    if not file_id or not file_id.isdigit():
        return jsonify({
            "code": 400,
            "msg": "Invalid or missing file ID",
            "data": None
        }), 400

    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 查询要删除的记录
            cursor.execute("SELECT * FROM file_records WHERE id = ?", (file_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({
                    "code": 404,
                    "msg": "File not found",
                    "data": None
                }), 404

            record = dict(record)

            # 获取文件路径并删除实际文件
            file_path = Path(BASE_DIR / "videoFile" / record['file_path'])
            if file_path.exists():
                try:
                    file_path.unlink()  # 删除文件
                    print(f"✅ 实际文件已删除: {file_path}")
                except Exception as e:
                    print(f"⚠️ 删除实际文件失败: {e}")
                    # 即使删除文件失败，也要继续删除数据库记录，避免数据不一致
            else:
                print(f"⚠️ 实际文件不存在: {file_path}")

            # 删除数据库记录
            cursor.execute("DELETE FROM file_records WHERE id = ?", (file_id,))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "File deleted successfully",
            "data": {
                "id": record['id'],
                "filename": record['filename']
            }
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("delete failed!"),
            "data": None
        }), 500

@app.route('/deleteAccount', methods=['GET'])
def delete_account():
    account_id = request.args.get('id')

    if not account_id or not account_id.isdigit():
        return jsonify({
            "code": 400,
            "msg": "Invalid or missing account ID",
            "data": None
        }), 400

    account_id = int(account_id)

    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 查询要删除的记录
            cursor.execute("SELECT * FROM user_info WHERE id = ?", (account_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({
                    "code": 404,
                    "msg": "account not found",
                    "data": None
                }), 404

            record = dict(record)

            # 删除关联的cookie文件
            if record.get('filePath'):
                cookie_file_path = Path(BASE_DIR / "cookiesFile" / record['filePath'])
                if cookie_file_path.exists():
                    try:
                        cookie_file_path.unlink()
                        print(f"✅ Cookie文件已删除: {cookie_file_path}")
                    except Exception as e:
                        print(f"⚠️ 删除Cookie文件失败: {e}")

            # 删除数据库记录
            cursor.execute("DELETE FROM user_info WHERE id = ?", (account_id,))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "account deleted successfully",
            "data": None
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": f"delete failed: {str(e)}",
            "data": None
        }), 500


# SSE 登录接口
@app.route('/login')
def login():
    # 1 小红书 2 视频号 3 抖音 4 快手
    type = request.args.get('type')
    # 账号名
    id = request.args.get('id')

    # 模拟一个用于异步通信的队列
    status_queue = Queue()
    active_queues[id] = status_queue

    def on_close():
        print(f"清理队列: {id}")
        del active_queues[id]
    # 启动异步任务线程
    thread = threading.Thread(target=run_async_function, args=(type,id,status_queue), daemon=True)
    thread.start()
    response = Response(sse_stream(status_queue,), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'  # 关键：禁用 Nginx 缓冲
    response.headers['Content-Type'] = 'text/event-stream'
    response.headers['Connection'] = 'keep-alive'
    return response

@app.route('/postVideo', methods=['POST'])
def postVideo():
    # 获取JSON数据
    data = request.get_json()

    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空", "data": None}), 400

    # 从JSON数据中提取fileList和accountList
    file_list = data.get('fileList', [])
    account_list = data.get('accountList', [])
    type = data.get('type')
    title = data.get('title')
    tags = data.get('tags')
    category = data.get('category')
    enableTimer = data.get('enableTimer')
    if category == 0:
        category = None
    productLink = data.get('productLink', '')
    productTitle = data.get('productTitle', '')
    thumbnail_path = data.get('thumbnail', '')
    is_draft = data.get('isDraft', False)  # 新增参数：是否保存为草稿

    videos_per_day = data.get('videosPerDay')
    daily_times = data.get('dailyTimes')
    start_days = data.get('startDays')

    # 参数校验
    if not file_list:
        return jsonify({"code": 400, "msg": "文件列表不能为空", "data": None}), 400
    if not account_list:
        return jsonify({"code": 400, "msg": "账号列表不能为空", "data": None}), 400
    if not type:
        return jsonify({"code": 400, "msg": "平台类型不能为空", "data": None}), 400
    if not title:
        return jsonify({"code": 400, "msg": "标题不能为空", "data": None}), 400

    # 打印获取到的数据（仅作为示例）
    print("File List:", file_list)
    print("Account List:", account_list)

    try:
        match type:
            case 1:
                post_video_xhs(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days)
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days, is_draft)
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, thumbnail_path, productLink, productTitle)
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days)
            case _:
                return jsonify({"code": 400, "msg": f"不支持的平台类型: {type}", "data": None}), 400

        # 返回响应给客户端
        return jsonify(
            {
                "code": 200,
                "msg": "发布任务已提交",
                "data": None
            }), 200
    except Exception as e:
        print(f"发布视频时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"发布失败: {str(e)}",
            "data": None
        }), 500


@app.route('/updateUserinfo', methods=['POST'])
def updateUserinfo():
    # 获取JSON数据
    data = request.get_json()

    # 从JSON数据中提取 type 和 userName
    user_id = data.get('id')
    type = data.get('type')
    userName = data.get('userName')
    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 更新数据库记录
            cursor.execute('''
                           UPDATE user_info
                           SET type     = ?,
                               userName = ?
                           WHERE id = ?;
                           ''', (type, userName, user_id))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "account update successfully",
            "data": None
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("update failed!"),
            "data": None
        }), 500

@app.route('/postVideoBatch', methods=['POST'])
def postVideoBatch():
    data_list = request.get_json()

    if not isinstance(data_list, list):
        return jsonify({"code": 400, "msg": "Expected a JSON array", "data": None}), 400
    for data in data_list:
        # 从JSON数据中提取fileList和accountList
        file_list = data.get('fileList', [])
        account_list = data.get('accountList', [])
        type = data.get('type')
        title = data.get('title')
        tags = data.get('tags')
        category = data.get('category')
        enableTimer = data.get('enableTimer')
        if category == 0:
            category = None
        productLink = data.get('productLink', '')
        productTitle = data.get('productTitle', '')
        is_draft = data.get('isDraft', False)

        videos_per_day = data.get('videosPerDay')
        daily_times = data.get('dailyTimes')
        start_days = data.get('startDays')
        # 打印获取到的数据（仅作为示例）
        print("File List:", file_list)
        print("Account List:", account_list)
        match type:
            case 1:
                post_video_xhs(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                               start_days)
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days, is_draft)
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, productLink, productTitle)
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days)
    # 返回响应给客户端
    return jsonify(
        {
            "code": 200,
            "msg": None,
            "data": None
        }), 200

# Cookie文件上传API
@app.route('/uploadCookie', methods=['POST'])
def upload_cookie():
    try:
        if 'file' not in request.files:
            return jsonify({
                "code": 400,
                "msg": "没有找到Cookie文件",
                "data": None
            }), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                "code": 400,
                "msg": "Cookie文件名不能为空",
                "data": None
            }), 400

        if not file.filename.endswith('.json'):
            return jsonify({
                "code": 400,
                "msg": "Cookie文件必须是JSON格式",
                "data": None
            }), 400

        # 获取账号信息
        account_id = request.form.get('id')
        platform = request.form.get('platform')

        if not account_id or not platform:
            return jsonify({
                "code": 400,
                "msg": "缺少账号ID或平台信息",
                "data": None
            }), 400

        # 从数据库获取账号的文件路径
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT filePath FROM user_info WHERE id = ?', (account_id,))
            result = cursor.fetchone()

        if not result:
            return jsonify({
                "code": 500,
                "msg": "账号不存在",
                "data": None
            }), 404

        # 保存上传的Cookie文件到对应路径
        cookie_file_path = Path(BASE_DIR / "cookiesFile" / result['filePath'])
        cookie_file_path.parent.mkdir(parents=True, exist_ok=True)

        file.save(str(cookie_file_path))

        # 更新数据库中的账号信息（可选，比如更新更新时间）
        # 这里可以根据需要添加额外的处理逻辑

        return jsonify({
            "code": 200,
            "msg": "Cookie文件上传成功",
            "data": None
        }), 200

    except Exception as e:
        print(f"上传Cookie文件时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"上传Cookie文件失败: {str(e)}",
            "data": None
        }), 500


# Cookie文件下载API
@app.route('/downloadCookie', methods=['GET'])
def download_cookie():
    try:
        file_path = request.args.get('filePath')
        if not file_path:
            return jsonify({
                "code": 500,
                "msg": "缺少文件路径参数",
                "data": None
            }), 400

        # 验证文件路径的安全性，防止路径遍历攻击
        cookie_file_path = Path(BASE_DIR / "cookiesFile" / file_path).resolve()
        base_path = Path(BASE_DIR / "cookiesFile").resolve()

        if not cookie_file_path.is_relative_to(base_path):
            return jsonify({
                "code": 500,
                "msg": "非法文件路径",
                "data": None
            }), 400

        if not cookie_file_path.exists():
            return jsonify({
                "code": 500,
                "msg": "Cookie文件不存在",
                "data": None
            }), 404

        # 返回文件
        return send_from_directory(
            directory=str(cookie_file_path.parent),
            path=cookie_file_path.name,
            as_attachment=True
        )

    except Exception as e:
        print(f"下载Cookie文件时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"下载Cookie文件失败: {str(e)}",
            "data": None
        }), 500


# 包装函数：在线程中运行异步函数
def run_async_function(type,id,status_queue):
    match type:
        case '1':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(xiaohongshu_cookie_gen(id, status_queue))
            loop.close()
        case '2':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(get_tencent_cookie(id,status_queue))
            loop.close()
        case '3':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(douyin_cookie_gen(id,status_queue))
            loop.close()
        case '4':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(get_ks_cookie(id,status_queue))
            loop.close()

# SSE 流生成器函数
def sse_stream(status_queue):
    while True:
        if not status_queue.empty():
            msg = status_queue.get()
            yield f"data: {msg}\n\n"
        else:
            # 避免 CPU 占满
            time.sleep(0.1)


def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sau_python():
    venv_python = Path(BASE_DIR / ".venv" / "bin" / "python")
    return str(venv_python if venv_python.exists() else Path(sys.executable))


def _sau_command(args):
    return [_sau_python(), str(Path(BASE_DIR / "sau_cli.py")), *args]


def _publish_task_timeout_seconds():
    raw_value = os.environ.get("SAU_PUBLISH_TASK_TIMEOUT_SECONDS", "")
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = DEFAULT_PUBLISH_TASK_TIMEOUT_SECONDS
    return max(60, value)


def _normalize_platform(platform):
    aliases = {
        "wechat_channels": "tencent",
        "weixin": "tencent",
        "shipinhao": "tencent",
    }
    return aliases.get(str(platform or ""), str(platform or ""))


def _frontend_platform(platform):
    return "wechat_channels" if platform == "tencent" else platform


def _platform_label(platform):
    return {
        "douyin": "抖音",
        "xiaohongshu": "小红书",
        "kuaishou": "快手",
        "tencent": "视频号",
        "bilibili": "Bilibili",
        "youtube": "YouTube",
    }.get(platform, platform)


def _account_file(platform, account_name):
    return Path(BASE_DIR / "cookies" / f"{platform}_{account_name}.json")


def _list_cli_accounts(platform):
    accounts = []
    cookies_dir = Path(BASE_DIR / "cookies")
    if not cookies_dir.exists():
        return accounts
    for path in cookies_dir.glob(f"{platform}_*.json"):
        account_name = path.stem.removeprefix(f"{platform}_")
        accounts.append({
            "id": f"{_frontend_platform(platform)}:{account_name}",
            "name": account_name,
            "platform": _frontend_platform(platform),
            "status": "可用",
            "remark": f"Cookie: {path.name}",
            "filePath": str(path),
        })
    return accounts


def _list_legacy_accounts():
    type_map = {
        1: "xiaohongshu",
        2: "wechat_channels",
        3: "douyin",
        4: "kuaishou",
    }
    db_path = Path(BASE_DIR / "db" / "database.db")
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT id, type, filePath, userName, status FROM user_info").fetchall()
    except Exception:
        return []
    accounts = []
    for row in rows:
        platform = type_map.get(int(row[1]), str(row[1]))
        accounts.append({
            "id": f"legacy:{row[0]}",
            "name": row[3],
            "platform": platform,
            "status": "可用" if int(row[4] or 0) == 1 else "失效",
            "remark": f"Cookie: {row[2]}",
            "filePath": row[2],
        })
    return accounts


def _delete_legacy_account(platform, account_name):
    type_map = {
        "xiaohongshu": 1,
        "wechat_channels": 2,
        "douyin": 3,
        "kuaishou": 4,
    }
    account_type = type_map.get(platform)
    if not account_type:
        return 0
    db_path = Path(BASE_DIR / "db" / "database.db")
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM user_info WHERE type = ? AND userName = ?",
                (account_type, account_name),
            )
            conn.commit()
            return cursor.rowcount or 0
    except Exception as exc:
        print(f"删除 legacy 账号失败: {exc}", flush=True)
        return 0


def _account_name_from_id(account_id):
    value = str(account_id)
    if ":" in value:
        return value.split(":", 1)[1]
    return value


def _image_data_url(path):
    image_path = Path(path)
    if not image_path.exists() or not image_path.is_file():
        return ""
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    return f"data:{mime_type};base64,{base64.b64encode(image_path.read_bytes()).decode('ascii')}"


def _extract_qrcode_path(line):
    match = re.search(r"(?:打开|保存到|open)\s*[:：]?\s*(?P<path>/[^\s，。]+?\.png)", _clean_terminal_text(line))
    return match.group("path") if match else ""


def _clean_terminal_text(value):
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value or "")).strip()


def _stream_process(command, platform, account_name, expect_qrcode=False):
    process = subprocess.Popen(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    qrcode_sent = False
    try:
        yield _sse({"type": "status", "message": f"子进程已启动 PID={process.pid}"})
        assert process.stdout is not None
        for line in process.stdout:
            text = _clean_terminal_text(line)
            if not text:
                continue
            print(f"子进程[{process.pid}] {text}", flush=True)
            yield _sse({"type": "status", "message": text})
            if expect_qrcode:
                qrcode_path = _extract_qrcode_path(text)
                if qrcode_path:
                    image_url = _image_data_url(qrcode_path)
                    if image_url:
                        qrcode_sent = True
                        yield _sse({"type": "qrcode", "imageUrl": image_url, "message": f"请使用{_platform_label(platform)}扫码登录"})
        return_code = process.wait()
    except GeneratorExit:
        if process.poll() is None:
            print(f"客户端断开，终止登录子进程 PID={process.pid}", flush=True)
            process.terminate()
        raise
    finally:
        if process.stdout:
            process.stdout.close()
    if return_code == 0:
        account_path = _account_file(platform, account_name)
        yield _sse({
            "type": "success",
            "message": "登录成功" if expect_qrcode else "执行成功",
            "account": {
                "id": f"{_frontend_platform(platform)}:{account_name}",
                "name": account_name,
                "platform": _frontend_platform(platform),
                "status": "可用",
                "remark": f"Cookie: {account_path.name}",
                "filePath": str(account_path),
            },
        })
        return
    if expect_qrcode and not qrcode_sent:
        yield _sse({"type": "status", "message": "未从子进程输出中识别到二维码图片，请查看服务日志或弹出的浏览器窗口"})
    yield _sse({"type": "error", "message": f"子进程执行失败，退出码 {return_code}"})


def _run_publish_task(task_id, platform, payload, account_names):
    def update(status=None, message=None, log=None):
        with publish_tasks_lock:
            task = publish_tasks[task_id]
            if status:
                task["status"] = status
            if message:
                task["message"] = message
            if log:
                task.setdefault("logs", []).append(log)

    file_paths = payload.get("filePaths") or []
    tags = ",".join(payload.get("topics") or [])
    description = payload.get("description") or ""
    schedule_at = payload.get("scheduleAt")
    title = payload.get("title") or ""
    kuaishou_promotion_title = (payload.get("kuaishouPromotionTaskTitle") or title).strip()
    browser_mode_flag = "--headed"
    content_type = payload.get("contentType") or "video"

    update(status="running", message="正在启动发布子进程")
    try:
        for account_name in account_names:
            if content_type == "note":
                image_paths = [str(Path(value)) for value in payload.get("imagePaths") or []]
                missing = [value for value in image_paths if not Path(value).is_file()]
                if missing:
                    raise RuntimeError(f"图片文件不存在: {missing[0]}")
                args = [
                    platform, "upload-note", "--account", account_name,
                    "--images", *image_paths,
                    "--title", title,
                    "--note", description,
                    browser_mode_flag,
                ]
                if tags:
                    args.extend(["--tags", tags])
                if schedule_at:
                    args.extend(["--schedule", schedule_at])
                command = _sau_command(args)
                update(message=f"正在发布图文到 {_platform_label(platform)} / {account_name}", log=" ".join(command))
                result = subprocess.run(
                    command,
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                    timeout=_publish_task_timeout_seconds(),
                )
                output = "\n".join(item for item in [result.stdout.strip(), result.stderr.strip()] if item)
                if output:
                    update(log=output[-4000:])
                if result.returncode != 0:
                    raise RuntimeError(output or f"图文发布子进程失败，退出码 {result.returncode}")
                continue
            for file_path in file_paths:
                path = Path(file_path)
                if not path.is_file():
                    raise RuntimeError(f"视频文件不存在: {file_path}")
                args = [platform, "upload-video", "--account", account_name, "--file", str(path), "--title", title]
                if platform == "bilibili":
                    args.extend(["--desc", description or title, "--tid", str(payload.get("tid") or 249)])
                else:
                    args.extend(["--desc", description, browser_mode_flag])
                if tags:
                    args.extend(["--tags", tags])
                if schedule_at:
                    args.extend(["--schedule", schedule_at])
                if platform == "kuaishou" and payload.get("kuaishouEnablePromotionTask"):
                    args.extend(["--promotion-task-title", kuaishou_promotion_title])
                command = _sau_command(args)
                update(message=f"正在发布 {path.name} 到 {_platform_label(platform)} / {account_name}", log=" ".join(command))
                result = subprocess.run(
                    command,
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                    timeout=_publish_task_timeout_seconds(),
                )
                output = "\n".join(item for item in [result.stdout.strip(), result.stderr.strip()] if item)
                if output:
                    update(log=output[-4000:])
                if result.returncode != 0:
                    raise RuntimeError(output or f"发布子进程失败，退出码 {result.returncode}")
        update(status="succeeded", message="发布任务执行完成")
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(
            item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item)
            for item in [exc.output, exc.stderr]
            if item
        ).strip()
        message = f"发布子进程超时，已停止等待（超过 {_publish_task_timeout_seconds()} 秒）"
        update(status="failed", message=message, log=output or message)
    except Exception as exc:
        update(status="failed", message=str(exc), log=str(exc))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5409, threaded=True)
