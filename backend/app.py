"""
Flask API 应用 - Discord 自动营销机器人系统

提供 REST API 接口：
- 账号管理 (CRUD + 启动/停止)
- 店铺管理 (CRUD + 抓取)
- 自动发送任务控制
"""
import asyncio
import threading
import logging
import requests
import sqlite3
from typing import Dict, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS

from config import config
from database import Database
from bot import DiscordBotClient, bot_clients
from auto_sender import (
    start_sending_task,
    stop_sending_task,
    get_task_status,
    pause_sending_task,
    resume_sending_task,
    load_task_state
)
from weidian_scraper import WeidianScraper, save_cookie_string
from license_manager import activate_license, clear_license, validate_local_license

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化 Flask 应用
app = Flask(__name__)
CORS(app)

# 初始化数据库
db = Database()
load_task_state(db)

# Discord bot 事件循环（在单独线程中运行）
bot_loop: asyncio.AbstractEventLoop = None
bot_thread: threading.Thread = None


# ============== 许可证 API ==============

@app.route('/api/license/status', methods=['GET'])
def get_license_status():
    """获取本地许可证状态"""
    try:
        activated, payload = validate_local_license()
        if activated:
            return jsonify({'success': True, 'activated': True, 'license': payload})
        return jsonify({'success': True, 'activated': False, 'error': payload})
    except Exception as e:
        logger.error(f"获取许可证状态失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/license/activate', methods=['POST'])
def activate_license_api():
    """激活许可证"""
    try:
        data = request.get_json() or {}
        license_key = data.get('key', '').strip()
        if not license_key:
            return jsonify({'success': False, 'error': '请输入许可证密钥'}), 400

        success, result = activate_license(license_key)
        if success:
            return jsonify({'success': True, **result})
        return jsonify({'success': False, 'error': result.get('message', '激活失败')}), 400
    except Exception as e:
        logger.error(f"激活许可证失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/license/clear', methods=['POST'])
def clear_license_api():
    """清除本地许可证"""
    try:
        if clear_license():
            return jsonify({'success': True, 'message': '许可证已清除'})
        return jsonify({'success': False, 'error': '清除许可证失败'}), 500
    except Exception as e:
        logger.error(f"清除许可证失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============== 日志 API ==============

@app.route('/api/logs/add', methods=['POST'])
def add_log():
    """接收客户端日志"""
    try:
        data = request.get_json() or {}
        message = data.get('message', '')
        module = data.get('module', '')
        func = data.get('func', '')
        level = data.get('level', 'INFO')
        logger.info("BOT_LOG [%s] %s %s %s", level, module, func, message)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"接收日志失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs/stream', methods=['GET'])
def stream_logs():
    """日志流占位（兼容旧前端）"""
    return jsonify({'success': True, 'logs': []})


def fetch_discord_username(token: str) -> str:
    """通过 Discord API 获取账号显示名称"""
    try:
        response = requests.get(
            'https://discord.com/api/v10/users/@me',
            headers={'Authorization': token},
            timeout=8
        )
        if response.status_code != 200:
            return ''
        data = response.json()
        if data.get('global_name'):
            return data.get('global_name', '')
        username = data.get('username', '')
        discriminator = data.get('discriminator', '')
        if username and discriminator and discriminator != '0':
            return f"{username}#{discriminator}"
        return username
    except Exception:
        return ''

def _get_account_by_token(token: str) -> Optional[Dict]:
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, username FROM discord_accounts WHERE token = ?',
                (token,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception:
        return None

def _start_account_by_id(account_id: int) -> Dict:
    account = db.get_account_by_id(account_id)
    if not account:
        return {'success': False, 'error': '账号不存在'}

    for client in bot_clients:
        if client.account_id == account_id and not client.is_closed():
            return {'success': False, 'error': '账号已在线'}

    client = DiscordBotClient(account_id=account_id)
    token = account['token']

    async def start_bot():
        try:
            await client.start(token, reconnect=True)
        except Exception as e:
            logger.error(f"账号 {account_id} 启动失败: {e}")

    asyncio.run_coroutine_threadsafe(start_bot(), bot_loop)
    bot_clients.append(client)
    db.update_account_status(account_id, 'online')
    return {'success': True, 'message': '账号启动中...'}

# ============== 账号管理 API ==============

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """获取所有 Discord 账号"""
    try:
        accounts = db.get_all_accounts()
        # 添加在线状态
        online_ids = {c.account_id for c in bot_clients if c.is_ready() and not c.is_closed()}
        for acc in accounts:
            acc['is_online'] = acc['id'] in online_ids
        return jsonify({'success': True, 'accounts': accounts})
    except Exception as e:
        logger.error(f"获取账号列表失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accounts', methods=['POST'])
def add_account():
    """添加新账号 (通过 token)"""
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        username = data.get('username', '').strip()

        if not token:
            return jsonify({'success': False, 'error': 'Token 不能为空'}), 400

        existing = _get_account_by_token(token)
        if existing:
            return jsonify({'success': False, 'error': '该账号已存在'}), 400

        if not username:
            username = fetch_discord_username(token)

        account_id = db.add_account(token=token, username=username)
        return jsonify({'success': True, 'account_id': account_id, 'message': '账号添加成功'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'error': '该账号已存在'}), 400
    except Exception as e:
        logger.error(f"添加账号失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    """删除账号"""
    try:
        # 先停止该账号的连接
        for client in bot_clients:
            if client.account_id == account_id:
                asyncio.run_coroutine_threadsafe(client.close(), bot_loop)
                bot_clients.remove(client)
                break

        db.delete_account(account_id)
        return jsonify({'success': True, 'message': '账号已删除'})
    except Exception as e:
        logger.error(f"删除账号失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/start', methods=['POST'])
def start_account(account_id):
    """启动账号连接"""
    try:
        result = _start_account_by_id(account_id)
        if result.get('success'):
            return jsonify(result)
        if result.get('error') == '账号不存在':
            return jsonify(result), 404
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"启动账号失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accounts/start_all', methods=['POST'])
def start_all_accounts():
    """一键启动所有账号"""
    try:
        accounts = db.get_all_accounts()
        started = 0
        skipped = 0
        failed = []

        for account in accounts:
            result = _start_account_by_id(account['id'])
            if result.get('success'):
                started += 1
            else:
                error = result.get('error', '')
                if error == '账号已在线':
                    skipped += 1
                else:
                    failed.append({'id': account['id'], 'error': error or '启动失败'})

        return jsonify({
            'success': True,
            'started': started,
            'skipped': skipped,
            'failed': failed
        })
    except Exception as e:
        logger.error(f"一键启动账号失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accounts/<int:account_id>/stop', methods=['POST'])
def stop_account(account_id):
    """停止账号连接"""
    try:
        for client in bot_clients:
            if client.account_id == account_id:
                asyncio.run_coroutine_threadsafe(client.close(), bot_loop)
                bot_clients.remove(client)
                db.update_account_status(account_id, 'offline')
                return jsonify({'success': True, 'message': '账号已停止'})

        return jsonify({'success': False, 'error': '账号未在线'}), 400
    except Exception as e:
        logger.error(f"停止账号失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============== 店铺管理 API ==============

@app.route('/api/shops', methods=['GET'])
def get_shops():
    """获取所有店铺"""
    try:
        shops = db.get_all_shops()
        return jsonify({'success': True, 'shops': shops})
    except Exception as e:
        logger.error(f"获取店铺列表失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/shops', methods=['POST'])
def add_shop():
    """添加新店铺"""
    try:
        data = request.get_json()
        shop_id = data.get('shop_id', '').strip()
        name = data.get('name', '').strip()

        if not shop_id:
            return jsonify({'success': False, 'error': '店铺ID不能为空'}), 400

        if not name:
            scraper = WeidianScraper()
            fetched_name = scraper.get_shop_name_by_shop_id(shop_id)
            name = fetched_name if fetched_name and fetched_name != '未知店铺' else f"店铺{shop_id}"

        result_id = db.add_shop(shop_id=shop_id, name=name)
        if result_id is None:
            return jsonify({'success': False, 'error': '店铺已存在'}), 400
        return jsonify({'success': True, 'id': result_id, 'message': '店铺添加成功'})
    except Exception as e:
        logger.error(f"添加店铺失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/shops/<int:shop_id>', methods=['DELETE'])
def delete_shop(shop_id):
    """删除店铺"""
    try:
        db.delete_shop(shop_id)
        return jsonify({'success': True, 'message': '店铺已删除'})
    except Exception as e:
        logger.error(f"删除店铺失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/shops/<int:shop_id>/scrape', methods=['POST'])
def scrape_shop(shop_id):
    """抓取店铺商品"""
    try:
        shop = db.get_shop_by_id(shop_id)
        if not shop:
            return jsonify({'success': False, 'error': '店铺不存在'}), 404

        # 启动抓取任务（在后台线程）
        def scrape_task():
            try:
                scraper = WeidianScraper()
                shop_name = shop.get('name') or ''
                if not shop_name or shop_name.startswith('店铺') or shop_name == '未知店铺':
                    fetched_name = scraper.get_shop_name_by_shop_id(shop['shop_id'])
                    if fetched_name and fetched_name != '未知店铺':
                        shop_name = fetched_name
                        db.update_shop_name(shop['id'], shop_name)

                item_ids = scraper.fetch_shop_item_ids(shop['shop_id'])
                if not item_ids:
                    logger.info(f"店铺 {shop['shop_id']} 未获取到商品，请检查Cookies或店铺ID")
                    db.update_shop_product_count(shop['shop_id'], 0)
                    return

                for item_id in item_ids:
                    product_url = f"https://weidian.com/item.html?itemID={item_id}"
                    product_data = {
                        'product_url': product_url,
                        'item_id': item_id,
                        'cnfans_url': f"https://cnfans.com/product?id={item_id}&platform=WEIDIAN",
                        'acbuy_url': (
                            "https://www.acbuy.com/product?url="
                            f"https%253A%252F%252Fweidian.com%252Fitem.html%253FitemID%253D{item_id}"
                            f"%2526spider_token%253D43fe&id={item_id}&source=WD"
                        ),
                        'shop_name': shop_name or shop.get('shop_id')
                    }
                    db.insert_product(product_data)

                db.update_shop_product_count(shop['shop_id'], len(item_ids))
                logger.info(f"店铺 {shop_name or shop['shop_id']} 抓取完成，共 {len(item_ids)} 个商品")
            except Exception as e:
                logger.error(f"抓取店铺失败: {e}")

        thread = threading.Thread(target=scrape_task, daemon=True)
        thread.start()

        return jsonify({'success': True, 'message': '抓取任务已启动'})
    except Exception as e:
        logger.error(f"启动抓取失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scrape/shop/status', methods=['GET'])
def scrape_shop_status():
    """抓取任务状态占位（兼容旧前端）"""
    return jsonify({'success': True, 'running': False})


@app.route('/api/shops/<int:shop_id>/products', methods=['GET'])
def get_shop_products(shop_id):
    """获取店铺的所有商品"""
    try:
        shop = db.get_shop_by_id(shop_id)
        if not shop:
            return jsonify({'success': False, 'error': '店铺不存在'}), 404

        products = db.get_products_by_shop(shop['name'])
        return jsonify({'success': True, 'products': products})
    except Exception as e:
        logger.error(f"获取商品列表失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/products', methods=['GET'])
def get_products():
    """商品列表占位（兼容旧前端）"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
    except ValueError:
        page = 1
        limit = 50
    return jsonify({'success': True, 'products': [], 'page': page, 'limit': limit, 'total': 0})


@app.route('/api/products/count', methods=['GET'])
def get_products_count():
    """商品数量占位（兼容旧前端）"""
    return jsonify({'success': True, 'count': 0})


# ============== 自动发送任务 API ==============

@app.route('/api/sender/start', methods=['POST'])
def start_sender():
    """启动自动发送任务"""
    try:
        data = request.get_json()
        shop_id = data.get('shopId')
        channel_id = data.get('channelId')
        account_ids = data.get('accountIds', [])
        interval = data.get('interval', config.DEFAULT_SEND_INTERVAL)

        # 参数验证
        if not shop_id:
            return jsonify({'success': False, 'error': '请选择店铺'}), 400
        if not channel_id:
            return jsonify({'success': False, 'error': '请输入目标频道ID'}), 400
        if not account_ids:
            return jsonify({'success': False, 'error': '请选择至少一个账号'}), 400

        # 验证间隔范围
        interval = max(config.MIN_SEND_INTERVAL, min(interval, config.MAX_SEND_INTERVAL))

        result = start_sending_task(
            shop_id=int(shop_id),
            channel_id=str(channel_id),
            account_ids=[int(id) for id in account_ids],
            interval=int(interval),
            db=db,
            bot_clients=bot_clients,
            bot_loop=bot_loop
        )

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        logger.error(f"启动发送任务失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sender/stop', methods=['POST'])
def stop_sender():
    """停止自动发送任务"""
    try:
        result = stop_sending_task(db)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        logger.error(f"停止发送任务失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sender/pause', methods=['POST'])
def pause_sender():
    """暂停自动发送任务"""
    try:
        result = pause_sending_task()
        if result['success']:
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"暂停发送任务失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sender/resume', methods=['POST'])
def resume_sender():
    """继续自动发送任务"""
    try:
        result = resume_sending_task(db=db, bot_clients=bot_clients, bot_loop=bot_loop)
        if result['success']:
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"继续发送任务失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sender/status', methods=['GET'])
def sender_status():
    """获取发送任务状态"""
    try:
        status = get_task_status()
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============== 系统 API ==============

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'success': True,
        'status': 'running',
        'bot_count': len(bot_clients),
        'online_bots': len([c for c in bot_clients if c.is_ready()])
    })


@app.route('/api/bot/cooldowns', methods=['GET'])
def bot_cooldowns():
    """账号冷却状态占位（兼容旧前端）"""
    return jsonify({'success': True, 'cooldowns': {}})


# ============== 设置 API ==============

@app.route('/api/settings/cookies', methods=['POST'])
def update_weidian_cookies():
    """更新微店 Cookies"""
    try:
        data = request.get_json() or {}
        cookie_string = data.get('cookies', '').strip()
        if not cookie_string:
            return jsonify({'success': False, 'error': 'Cookies 不能为空'}), 400
        if save_cookie_string(cookie_string):
            return jsonify({'success': True, 'message': 'Cookies 已更新'})
        return jsonify({'success': False, 'error': '保存Cookies失败'}), 500
    except Exception as e:
        logger.error(f"更新Cookies失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============== Bot 线程管理 ==============

def run_bot_loop():
    """在单独线程中运行 Discord bot 事件循环"""
    global bot_loop
    bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(bot_loop)
    logger.info("Discord bot 事件循环已启动")
    bot_loop.run_forever()


def start_bot_thread():
    """启动 bot 线程"""
    global bot_thread
    bot_thread = threading.Thread(target=run_bot_loop, daemon=True)
    bot_thread.start()
    logger.info("Bot 线程已启动")


# ============== 主入口 ==============

if __name__ == '__main__':
    import signal
    import sys
    import time

    def shutdown_handler(signum, frame):
        """处理关闭信号，清理资源"""
        logger.info("收到关闭信号，正在停止服务...")
        try:
            stop_sending_task()
        except Exception:
            pass

        if bot_loop and bot_loop.is_running():
            async def close_bots():
                for client in list(bot_clients):
                    try:
                        await client.close()
                    except Exception:
                        continue

            future = asyncio.run_coroutine_threadsafe(close_bots(), bot_loop)
            try:
                future.result(timeout=5)
            except Exception:
                pass
            try:
                bot_loop.call_soon_threadsafe(bot_loop.stop)
            except Exception:
                pass

        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # 启动 bot 事件循环线程
    start_bot_thread()

    # 等待事件循环启动
    time.sleep(1)

    logger.info(f"启动 Flask 服务: {config.FLASK_HOST}:{config.FLASK_PORT}")
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,
        use_reloader=False,
        threaded=True
    )
