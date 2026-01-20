"""
自动发送任务调度模块 - Discord 商品链接自动发送

实现功能：
1. 从数据库读取指定店铺的所有商品
2. 获取用户选择的多个 Discord 账号
3. 轮询算法：每发一条，换一个账号 (Round Robin)
4. 频率控制：发送后等待指定秒数
5. 支持随时中断任务
"""
import asyncio
import logging
import re
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# 全局变量控制任务状态
current_task: Optional[asyncio.Task] = None
stop_sender_event = asyncio.Event()
stop_sender_reason: Optional[str] = None
task_status = {
    'is_running': False,
    'is_paused': False,
    'shop_id': None,
    'channel_id': None,
    'account_ids': [],
    'interval': None,
    'total_products': 0,
    'sent_count': 0,
    'current_product': None,
    'current_account': None,
    'started_at': None,
    'last_sent_at': None,
    'error': None,
    'next_product_index': 0,
    'next_account_index': 0
}


def get_task_status() -> Dict:
    """获取当前任务状态"""
    return task_status.copy()


def reset_task_status():
    """重置任务状态"""
    global task_status
    task_status = {
        'is_running': False,
        'is_paused': False,
        'shop_id': None,
        'channel_id': None,
        'account_ids': [],
        'interval': None,
        'total_products': 0,
        'sent_count': 0,
        'current_product': None,
        'current_account': None,
        'started_at': None,
        'last_sent_at': None,
        'error': None,
        'next_product_index': 0,
        'next_account_index': 0
    }


def _extract_item_id(product: Dict) -> str:
    item_id = product.get('item_id')
    if item_id:
        return str(item_id)
    url = product.get('product_url') or product.get('cnfans_url') or product.get('acbuy_url') or ''
    if url:
        match = re.search(r'itemID=(\d+)', url)
        if match:
            return match.group(1)
        match = re.search(r'[?&]id=(\d+)', url)
        if match:
            return match.group(1)
    return ''

def _persist_task_state(db) -> None:
    try:
        db.save_sender_task_state({
            'is_running': task_status.get('is_running'),
            'is_paused': task_status.get('is_paused'),
            'shop_id': task_status.get('shop_id'),
            'channel_id': task_status.get('channel_id'),
            'account_ids': task_status.get('account_ids', []),
            'interval': task_status.get('interval'),
            'total_products': task_status.get('total_products', 0),
            'sent_count': task_status.get('sent_count', 0),
            'next_product_index': task_status.get('next_product_index', 0),
            'next_account_index': task_status.get('next_account_index', 0),
            'current_product': task_status.get('current_product'),
            'current_account': task_status.get('current_account'),
            'started_at': task_status.get('started_at'),
            'last_sent_at': task_status.get('last_sent_at')
        })
    except Exception:
        return

def _has_online_bots(bot_clients: List, account_ids: List[int]) -> bool:
    if not account_ids:
        return False
    for client in bot_clients:
        if (
            hasattr(client, 'account_id')
            and client.account_id in account_ids
            and client.is_ready()
            and not client.is_closed()
        ):
            return True
    return False

def load_task_state(db) -> None:
    """加载上次任务状态（用于恢复）"""
    state = db.get_sender_task_state()
    if not state or not state.get('shop_id') or not state.get('channel_id'):
        return

    reset_task_status()
    task_status['shop_id'] = state.get('shop_id')
    task_status['channel_id'] = state.get('channel_id')
    task_status['account_ids'] = state.get('account_ids', [])
    task_status['interval'] = state.get('interval')
    task_status['total_products'] = state.get('total_products', 0)
    task_status['sent_count'] = state.get('sent_count', 0)
    task_status['current_product'] = state.get('current_product')
    task_status['current_account'] = state.get('current_account')
    task_status['started_at'] = state.get('started_at')
    task_status['last_sent_at'] = state.get('last_sent_at')
    task_status['next_product_index'] = state.get('next_product_index', 0)
    task_status['next_account_index'] = state.get('next_account_index', 0)

    if state.get('is_running'):
        task_status['is_running'] = False
        task_status['is_paused'] = True
        _persist_task_state(db)
    else:
        task_status['is_paused'] = bool(state.get('is_paused'))


async def auto_send_loop(
    shop_id: int,
    target_channel_id: str,
    selected_account_ids: List[int],
    interval: int,
    db,
    bot_clients: List,
    start_product_index: int = 0,
    start_account_index: int = 0
):
    """
    自动发送循环任务

    :param shop_id: 选中的店铺ID（用于从数据库捞商品）
    :param target_channel_id: 目标 Discord 频道 ID
    :param selected_account_ids: 用户勾选的 Account ID 列表 [1, 2, 5]
    :param interval: 发送间隔（秒）
    :param db: 数据库实例
    :param bot_clients: 机器人客户端列表
    """
    global task_status

    logger.info(f"启动自动发送: 店铺{shop_id} -> 频道{target_channel_id}，间隔{interval}s")

    task_status['is_running'] = True
    task_status['is_paused'] = False
    task_status['shop_id'] = shop_id
    task_status['channel_id'] = target_channel_id
    task_status['account_ids'] = selected_account_ids
    task_status['interval'] = interval
    task_status['started_at'] = datetime.now().isoformat()
    task_status['error'] = None
    task_status['next_product_index'] = max(0, start_product_index)
    task_status['next_account_index'] = max(0, start_account_index)
    _persist_task_state(db)

    try:
        # 1. 获取该店铺所有商品链接
        shop_info = db.get_shop_by_id(shop_id)
        if not shop_info:
            task_status['error'] = f"店铺 {shop_id} 不存在"
            logger.error(task_status['error'])
            return

        shop_name = shop_info.get('name', '')

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, product_url, title, cnfans_url, item_id FROM products WHERE shop_name = ?",
                (shop_name,)
            )
            products = [dict(row) for row in cursor.fetchall()]

        if not products:
            task_status['error'] = f"店铺 '{shop_name}' 没有商品数据，请先执行抓取"
            logger.warning(task_status['error'])
            return

        task_status['total_products'] = len(products)
        logger.info(f"待发送商品数: {len(products)}")
        if task_status['next_product_index'] >= len(products):
            task_status['sent_count'] = len(products)
            task_status['current_product'] = None
            _persist_task_state(db)
            logger.info("商品已发送完毕，无需继续")
            return

        # 2. 筛选出可用的在线 Bot 客户端
        active_bots = [
            client for client in bot_clients
            if hasattr(client, 'account_id')
            and client.account_id in selected_account_ids
            and client.is_ready()
            and not client.is_closed()
        ]

        if not active_bots:
            task_status['error'] = "没有选中的账号在线，请先启动账号"
            logger.error(task_status['error'])
            return

        logger.info(f"可用账号数: {len(active_bots)}")

        product_idx = task_status['next_product_index']
        bot_idx = task_status['next_account_index']
        task_status['sent_count'] = product_idx

        # 3. 循环发送
        while not stop_sender_event.is_set():
            if product_idx >= len(products):
                logger.info("所有商品已发送完毕，任务结束")
                break

            # 获取当前要发的商品
            product = products[product_idx]
            link_to_send = product.get('product_url', '')
            title = product.get('title', '未知商品')
            message_content = f"{title}\n{link_to_send}"

            # 获取当前轮换的账号 (Round Robin)
            current_bot = active_bots[bot_idx % len(active_bots)]

            task_status['current_product'] = _extract_item_id(product) or title[:50]
            task_status['current_account'] = getattr(current_bot, 'user', None)
            if task_status['current_account']:
                task_status['current_account'] = str(task_status['current_account'])
            task_status['next_product_index'] = product_idx
            task_status['next_account_index'] = bot_idx
            _persist_task_state(db)

            try:
                channel = current_bot.get_channel(int(target_channel_id))
                if channel:
                    await channel.send(message_content)
                    task_status['sent_count'] += 1
                    task_status['last_sent_at'] = datetime.now().isoformat()
                    task_status['next_product_index'] = product_idx + 1
                    task_status['next_account_index'] = bot_idx + 1
                    _persist_task_state(db)
                    logger.info(
                        f"✅ 账号 {current_bot.user.name if current_bot.user else 'Unknown'} "
                        f"发送成功 ({task_status['sent_count']}/{task_status['total_products']}): {title[:30]}..."
                    )
                else:
                    logger.error(
                        f"账号 {current_bot.user.name if current_bot.user else 'Unknown'} "
                        f"找不到频道 {target_channel_id}"
                    )
            except Exception as e:
                logger.error(f"发送失败: {e}")
                # 继续下一条，不中断任务

            # 索引递增
            product_idx += 1
            bot_idx += 1

            # 等待间隔（支持随时中断）
            try:
                await asyncio.wait_for(
                    stop_sender_event.wait(),
                    timeout=float(interval)
                )
                # 如果 wait 返回了，说明 event 被 set 了，收到停止信号
                logger.info("收到停止信号，任务中断")
                break
            except asyncio.TimeoutError:
                # 超时意味着时间到了，继续下一次循环
                continue

    except asyncio.CancelledError:
        logger.info("任务被取消")
    except Exception as e:
        task_status['error'] = str(e)
        logger.error(f"自动发送任务异常: {e}")
    finally:
        task_status['is_running'] = False
        if stop_sender_reason == 'pause':
            task_status['is_paused'] = True
            _persist_task_state(db)
        else:
            task_status['is_paused'] = False
            db.clear_sender_task_state()
        logger.info("自动发送任务结束")


def start_sending_task(
    shop_id: int,
    channel_id: str,
    account_ids: List[int],
    interval: int,
    db,
    bot_clients: List,
    bot_loop: asyncio.AbstractEventLoop,
    start_product_index: int = 0,
    start_account_index: int = 0,
    resume: bool = False
) -> Dict:
    """
    启动自动发送任务（从 Flask 线程调用）

    :param shop_id: 店铺 ID
    :param channel_id: 目标频道 ID
    :param account_ids: 账号 ID 列表
    :param interval: 发送间隔（秒）
    :param db: 数据库实例
    :param bot_clients: 机器人客户端列表
    :param bot_loop: Discord bot 的事件循环
    :return: 操作结果
    """
    global current_task, stop_sender_event

    if task_status['is_running'] or (task_status['is_paused'] and not resume):
        return {'success': False, 'error': '已有任务正在运行或已暂停，请先停止或继续'}

    # 重置停止事件
    stop_sender_event.clear()
    global stop_sender_reason
    stop_sender_reason = None
    reset_task_status()
    task_status['shop_id'] = shop_id
    task_status['channel_id'] = channel_id
    task_status['account_ids'] = account_ids
    task_status['interval'] = interval
    task_status['next_product_index'] = max(0, start_product_index)
    task_status['next_account_index'] = max(0, start_account_index)
    if resume:
        task_status['sent_count'] = max(0, start_product_index)

    # 在 bot 的事件循环中创建任务
    try:
        future = asyncio.run_coroutine_threadsafe(
            auto_send_loop(
                shop_id=shop_id,
                target_channel_id=channel_id,
                selected_account_ids=account_ids,
                interval=interval,
                db=db,
                bot_clients=bot_clients,
                start_product_index=start_product_index,
                start_account_index=start_account_index
            ),
            bot_loop
        )
        logger.info("自动发送任务已提交到事件循环")
        return {'success': True, 'message': '自动发送任务已启动'}
    except Exception as e:
        logger.error(f"启动任务失败: {e}")
        return {'success': False, 'error': str(e)}


def stop_sending_task(db=None) -> Dict:
    """
    停止自动发送任务

    :return: 操作结果
    """
    global stop_sender_event, stop_sender_reason

    if not task_status['is_running'] and not task_status['is_paused']:
        return {'success': False, 'error': '当前没有运行中的任务'}

    stop_sender_reason = 'stop'
    stop_sender_event.set()
    task_status['is_paused'] = False
    if db:
        db.clear_sender_task_state()
    logger.info("已发送停止信号")
    return {'success': True, 'message': '任务停止指令已发送'}


def pause_sending_task() -> Dict:
    """暂停自动发送任务"""
    global stop_sender_event, stop_sender_reason

    if not task_status['is_running']:
        return {'success': False, 'error': '当前没有运行中的任务'}

    stop_sender_reason = 'pause'
    stop_sender_event.set()
    logger.info("已发送暂停信号")
    return {'success': True, 'message': '任务暂停指令已发送'}


def resume_sending_task(db, bot_clients: List, bot_loop: asyncio.AbstractEventLoop) -> Dict:
    """继续自动发送任务"""
    state = db.get_sender_task_state()
    if not state or not state.get('shop_id') or not state.get('channel_id'):
        return {'success': False, 'error': '没有可继续的任务'}
    if task_status['is_running']:
        return {'success': False, 'error': '任务正在运行中'}

    account_ids = [int(item) for item in state.get('account_ids', [])]
    if not _has_online_bots(bot_clients, account_ids):
        return {'success': False, 'error': '没有选中的账号在线，请先启动账号'}

    return start_sending_task(
        shop_id=int(state['shop_id']),
        channel_id=str(state['channel_id']),
        account_ids=account_ids,
        interval=int(state.get('interval') or 60),
        db=db,
        bot_clients=bot_clients,
        bot_loop=bot_loop,
        start_product_index=int(state.get('next_product_index') or 0),
        start_account_index=int(state.get('next_account_index') or 0),
        resume=True
    )
