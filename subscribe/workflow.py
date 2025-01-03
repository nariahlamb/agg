# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import json
import os
import re
from dataclasses import dataclass

import renewal
import utils
from airport import ANOTHER_API_PREFIX, AirPort
from logger import logger
from origin import Origin
from push import PushTo


@dataclass
class TaskConfig:
    # 任务名
    name: str

    # subconverter程序名
    bin_name: str

    # 任务编号
    taskid: int = -1

    # 网址域名
    domain: str = ""

    # 订阅地址
    sub: str = ""

    # 任务编号
    index: int = 1

    # 失败重试次数
    retry: int = 3

    # 最高允许倍率
    rate: float = 30.0

    # 标签
    tag: str = ""

    # 套餐续期配置
    renew: dict = None

    # 优惠码
    coupon: str = ""

    # 节点重命名规则
    rename: str = "{flag}-{country}-{type}-{index}"

    # 节点排除规则
    exclude: str = "(?i)(到期|流量|Expire|Traffic|时间|官网|引导页?|网(\\s+)?址|官址|地址|导航|平台|网站|域名|付费|优惠|折扣|刷新|获取|订阅|群|取消|禁|产品|余额|更新|回国|telegram|t.me|频道|电报|售后|反馈|工单|私聊|维护|升级|邮箱|关闭|耗尽|关机|停机|故障|宕机|调整|修复|解决|重新|拥挤|测试|公测|过年|test|测速|https?://|重置|剩余|特殊|⭕|1️⃣|购买|暂时|临时|下载|调试|检查|干扰|热度|公告|官方|推迟|阻断|采购|好用|福利|精品|商用|Prepaid|疫情|感染|下架|投诉|屏蔽|邀请|欢迎|机场|返利|推广|佣金|广告|破解|不同|骗|店|YYDS|真香|关注|谢谢|大家|永久|浏览器|月付|打开|包月|套餐|以上|以下|通知|注册|活动|转换|保证|每天|分享|倒卖|搬运|苏小柠|王者荣耀|代练|去除|不合适|尽快|绑定|临时域名|禁止|登录|激活|账号|恢复|更换|搜索|失联|发布)"
    include: str = "(?i)(日本|香港|台湾|新加坡|美国|英国|gpt|chatgpt|解锁|x|奈飞|netflix)"

    # ChatGPT连通性测试节点过滤规则
    chatgpt: dict = None

    # 是否检测节点存活状态
    liveness: bool = True

    # 是否强制开启 tls 及阻止跳过证书验证
    disable_insecure: bool = False

    # 覆盖subconverter默认exclude规则
    ignorede: bool = True

    # 是否允许特殊协议
    special_protocols: bool = False

    # 对于具有邮箱域名白名单且需要验证码的情况，是否使用 Gmail 别名邮箱尝试，为 True 时表示不使用
    rigid: bool = False

    # 是否丢弃可能需要人机验证的站点
    chuck: bool = False

    # 邀请码
    invite_code: str = ""

    # 接口地址前缀，如 /api/v1/ 或 /api?scheme=
    api_prefix: str = "/api/v1/"


def execute(task_conf: TaskConfig) -> list:
    if not task_conf or not isinstance(task_conf, TaskConfig):
        return []

    obj = AirPort(
        name=task_conf.name,
        site=task_conf.domain,
        sub=task_conf.sub,
        rename=task_conf.rename,
        exclude=task_conf.exclude,
        include=task_conf.include,
        liveness=task_conf.liveness,
        coupon=task_conf.coupon,
        api_prefix=task_conf.api_prefix,
    )

    logger.info(f"start fetch proxy: name=[{task_conf.name}]\tid=[{task_conf.index}]\tdomain=[{obj.ref}]")

    # 套餐续期
    if task_conf.renew:
        sub_url = renewal.add_traffic_flow(
            domain=obj.ref,
            params=task_conf.renew,
            jsonify=obj.api_prefix == ANOTHER_API_PREFIX,
        )
        if sub_url and not obj.registed:
            obj.registed = True
            obj.sub = sub_url

    cookie, authorization = obj.get_subscribe(
        retry=task_conf.retry,
        rigid=task_conf.rigid,
        chuck=task_conf.chuck,
        invite_code=task_conf.invite_code,
    )

    proxies = obj.parse(
        cookie=cookie,
        auth=authorization,
        retry=task_conf.retry,
        rate=task_conf.rate,
        bin_name=task_conf.bin_name,
        tag=task_conf.tag,
        disable_insecure=task_conf.disable_insecure,
        ignore_exclude=task_conf.ignorede,
        chatgpt=task_conf.chatgpt,
        special_protocols=task_conf.special_protocols,
    )

    logger.info(
        f"finished fetch proxy: name=[{task_conf.name}]\tid=[{task_conf.index}]\tdomain=[{obj.ref}]\tcount=[{len(proxies)}]"
    )
    
    # 提取纯节点信息
    node_list = []
    for proxy in proxies:
        if isinstance(proxy, dict):
            node_info = {
                "name": proxy.get("name"),
                "server": proxy.get("server"),
                "port": proxy.get("port"),
                "type": proxy.get("type"),
                # 根据你的节点信息结构添加其他需要的字段
            }
            node_list.append(node_info)

    # 创建纯节点文件并推送到 Gist
    if node_list:
        push_node_list(node_list=node_list, task_conf=task_conf)

    return proxies


def push_node_list(node_list: list, task_conf: TaskConfig):
    """
    将纯节点列表推送到 Gist
    """
    if not node_list:
       logger.error("[PushError] nodes list is empty.")
       return
    
    push_config = {
        "type": "gist",
        "url": "https://api.github.com/gists",  # Gist API URL
        "method": "post",
        "token": os.environ.get("GITHUB_TOKEN"),  # 从环境变量中获取 GitHub Token
        "filename": f"{task_conf.name}_nodes.json", # 设置文件名
        "description": f"{task_conf.name} Pure Node List", # 设置描述
        "group": "nodes-list"  # 设置分组
    }
    
    if not push_config.get("token"):
        logger.error("[PushError] github token not found.")
        return
    
    push = PushTo(
       push_type="gist",
       gist_url="https://api.github.com/gists",
       gist_token=push_config.get("token")
    )
    
    try:
        content = json.dumps(node_list, indent=2, ensure_ascii=False)
        push.push_to(content=content, push_conf=push_config, group="nodes-list")
        logger.info(f"[PushInfo] pushed node list to gist: {push_config.get('filename')}")
    except Exception as e:
       logger.error(f"[PushError] push node list failed: {e}")


def executewrapper(task_conf: TaskConfig) -> tuple[int, list]:
    if not task_conf:
        return (-1, [])

    taskid = task_conf.taskid
    proxies = execute(task_conf=task_conf)
    return (taskid, proxies)


def liveness_fillter(proxies: list) -> tuple[list, list]:
    if not list:
        return [], []

    checks, nochecks = [], []
    for p in proxies:
        if not isinstance(p, dict):
            continue

        liveness = p.pop("liveness", True)
        if liveness:
            checks.append(p)
        else:
            p.pop("sub", "")
            p.pop("chatgpt", False)
            nochecks.append(p)

    return checks, nochecks


def cleanup(filepath: str = "", filenames: list = []) -> None:
    if not filepath or not filenames:
        return

    for name in filenames:
        filename = os.path.join(filepath, name)
        if os.path.exists(filename):
            os.remove(filename)


def dedup_task(tasks: list) -> list:
    if not tasks:
        return []
    items = []
    for task in tasks:
        if not exists(tasks=items, task=task):
            items.append(task)

    return items


def exists(tasks: list, task: TaskConfig) -> bool:
    if not isinstance(task, TaskConfig):
        logger.error(f"[DedupError] need type 'TaskConfig' but got type '{type(task)}'")
        return True
    if not tasks:
        return False

    found = False
    for item in tasks:
        if task.sub != "":
            if task.sub == item.sub:
                found = True
        else:
            if task.domain == item.domain and task.index == item.index:
                found = True

        if found:
            if not item.rename:
                item.rename = task.rename
            if task.exclude:
                item.exclude = "|".join([item.exclude, task.exclude]).removeprefix("|")
            if task.include:
                item.include = "|".join([item.include, task.include]).removeprefix("|")
        break

    return found


def merge_config(configs: list) -> list:
    def judge_exists(raw: dict, target: dict) -> bool:
        if not raw or not target:
            return False

        rsub = raw.get("sub").strip()
        tsub = target.get("sub", "")
        if not tsub:
            if rsub:
                return False
            return raw.get("domain", "").strip() == target.get("domain", "").strip()
        if isinstance(tsub, str):
            return rsub == tsub.strip()
        for sub in tsub:
            if rsub == sub.strip():
                return True
        return False

    if not configs:
        return []
    items = []
    for conf in configs:
        if not isinstance(conf, dict):
            logger.error(f"[MergeError] need type 'dict' but got type '{type(conf)}'")
            continue

        sub = conf.get("sub", "")
        if isinstance(sub, list) and len(sub) <= 1:
            sub = sub[0] if sub else ""

        # 人工维护配置，无需合并
        if isinstance(sub, list) or conf.get("renew", {}):
            items.append(conf)
            continue

        found = False
        conf["sub"] = sub
        for item in items:
            found = judge_exists(raw=conf, target=item)
            if found:
                if conf.get("errors", 0) > item.get("errors", 0):
                    item["errors"] = conf.get("errors", 0)
                if item.get("debut", False):
                    item["debut"] = conf.get("debut", False)
                if not item.get("rename", ""):
                    item["rename"] = conf.get("rename", "")
                if conf.get("exclude", ""):
                    item["exclude"] = "|".join([item.get("exclude", ""), conf.get("exclude", "")]).removeprefix("|")
                if conf.get("include", ""):
                    item["include"] = "|".join([item.get("include", ""), conf.get("include", "")]).removeprefix("|")

                break

        if not found:
            items.append(conf)

    return items


def refresh(config: dict, push: PushTo, alives: dict, filepath: str = "", skip_remark: bool = False) -> None:
    if not config or not push:
        logger.error("[UpdateError] cannot update remote config because content is empty")
        return

    # mark invalid crawled subscription
    invalidsubs = None if (skip_remark or not alives) else [k for k, v in alives.items() if not v]
    if invalidsubs:
        crawledsub = config.get("crawl", {}).get("persist", {}).get("subs", "")
        threshold = max(config.get("threshold", 1), 1)
        pushconf = config.get("groups", {}).get(crawledsub, {})
        if push.validate(push_conf=pushconf):
            url = push.raw_url(push_conf=pushconf)
            content = utils.http_get(url=url)
            try:
                data, count = json.loads(content), 0
                for sub in invalidsubs:
                    record = data.pop(sub, None)
                    if not record:
                        continue

                    defeat = record.get("defeat", 0) + 1
                    count += 1
                    if defeat <= threshold and standard_sub(url=sub):
                        record["defeat"] = defeat
                        data[sub] = record

                if count > 0:
                    content = json.dumps(data)
                    push.push_to(content=content, push_conf=pushconf, group="crawled-remark")
                    logger.info(f"[UpdateInfo] found {count} invalid crawled subscriptions")
            except:
                logger.error(f"[UpdateError] remark invalid crawled subscriptions failed")

    update_conf = config.get("update", {})
    if not update_conf.get("enable", False):
        logger.debug("[UpdateError] skip update remote config because enable=[False]")
        return

    if not push.validate(push_conf=update_conf):
        logger.error(f"[UpdateError] update config is invalidate")
        return

    domains = merge_config(configs=config.get("domains", []))
    if alives:
        sites = []
        for item in domains:
            source = item.get("origin", "")
            sub = item.get("sub", "")
            if isinstance(sub, list) and len(sub) <= 1:
                sub = sub[0] if sub else ""
            if source in [Origin.TEMPORARY.name, Origin.OWNED.name] or isinstance(sub, list) or alives.get(sub, False):
                item.pop("errors", None)
                item.pop("debut", None)
                sites.append(item)
                continue

            errors = item.get("errors", 1)
            expire = Origin.get_expire(source)
            if errors < expire and not item.get("debut", False):
                item.pop("debut", None)
                sites.append(item)

        config["domains"] = sites
        domains = config.get("domains", [])

    if not domains:
        logger.error("[UpdateError] skip update remote config because domians is empty")
        return

    content = json.dumps(config)
    if filepath:
        directory = os.path.abspath(os.path.dirname(filepath))
        os.makedirs(directory, exist_ok=True)
        with open(filepath, "w+", encoding="UTF8") as f:
            f.write(content)
            f.flush()

    push.push_to(content=content, push_conf=update_conf, group="update")


def standard_sub(url: str) -> bool:
    regex = r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu|clash)=\d))"
    return re.match(regex, url, flags=re.I) is not None
