#!/usr/bin/env python3
"""
微信公众号 API 调用

- 图片上传(封面图 / 正文图 / 贴图素材图)
- 新建草稿(图文 news / 贴图 newspic 两种)
- 一站式发布便捷函数 publish_article / publish_newspic

对瞬时错误(5xx / Timeout)自动重试;对应用层错误(如 40164 IP 白名单)直接抛出不重试。
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests

from engine.config import get_config, set_account
from wechat_token import get_access_token
from engine.logger import get_logger

logger = get_logger(__name__)


API_TIMEOUT_SEC = 30
API_RETRIES = 2
API_BASE = "https://api.weixin.qq.com/cgi-bin"


# ============================================================
# 共享工具
# ============================================================

_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _guess_mime(path: Path) -> str:
    """根据扩展名推断 MIME 类型,未知扩展名兜底 image/jpeg。"""
    return _MIME_MAP.get(path.suffix.lower(), "image/jpeg")


def _api_request_with_retry(method: str, url: str, retries: int = API_RETRIES, **kwargs) -> requests.Response:
    """
    HTTP 调用 + 5xx/Timeout 重试;4xx 不重试(是客户端问题)。
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = requests.request(method, url, timeout=API_TIMEOUT_SEC, **kwargs)
            resp.encoding = "utf-8"  # 强制 UTF-8，避免 requests 误判编码导致中文乱码
            if 500 <= resp.status_code < 600 and attempt < retries:
                logger.warning(
                    "API 请求返回 %d (%s)，重试 %d/%d",
                    resp.status_code, url.split("?")[0], attempt + 1, retries,
                )
                time.sleep(1.5 ** attempt)
                continue
            return resp
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            if attempt < retries:
                logger.warning(
                    "API 请求超时/连接失败 (%s): %s，重试 %d/%d",
                    url.split("?")[0], e, attempt + 1, retries,
                )
                time.sleep(1.5 ** attempt)
                continue
            logger.error("API 请求最终失败 (%s): %s", url.split("?")[0], e)
            raise
    raise last_exc or RuntimeError("API 请求失败(未知原因)")


# ============================================================
# 图片上传
# ============================================================

def upload_thumb_image(image_path: Union[str, Path]) -> str:
    """
    上传封面图(永久素材)。

    ⚠️ 占用公众号永久素材配额(图片上限 5000 个)。
    返回的 media_id 用于创建草稿时的 thumb_media_id。
    """
    token = get_access_token()
    url = f"{API_BASE}/material/add_material?access_token={token}&type=image"

    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    mime_type = _guess_mime(image_path)

    with open(image_path, "rb") as f:
        files = {"media": (image_path.name, f, mime_type)}
        resp = _api_request_with_retry("POST", url, files=files)

    resp.raise_for_status()
    data = resp.json()

    if "media_id" not in data:
        error_msg = data.get("errmsg", "未知错误")
        error_code = data.get("errcode", -1)
        logger.error("上传封面图失败 [%d]: %s (文件: %s)", error_code, error_msg, image_path)
        raise RuntimeError(f"上传封面图失败 [{error_code}]: {error_msg}")

    logger.info("封面图上传成功: media_id=%s (文件: %s)", data["media_id"], image_path.name)
    return data["media_id"]


def upload_newspic_image(image_path: Union[str, Path]) -> str:
    """
    上传贴图(图片消息)所需的素材图,返回 media_id。

    ⚠️ 和 `upload_thumb_image` 一样走 `add_material` 永久素材接口,
    占用公众号永久素材配额(图片上限 5000 个)。
    newspic 的 `image_info.image_list[].image_media_id` 必须是永久素材 media_id,
    不能用 `uploadimg` 返回的 URL。

    每个贴图 5-10 张图就要占掉 5-10 个素材名额,发布前心里有数。
    """
    token = get_access_token()
    url = f"{API_BASE}/material/add_material?access_token={token}&type=image"

    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    mime_type = _guess_mime(image_path)

    with open(image_path, "rb") as f:
        files = {"media": (image_path.name, f, mime_type)}
        resp = _api_request_with_retry("POST", url, files=files)

    resp.raise_for_status()
    data = resp.json()

    if "media_id" not in data:
        error_msg = data.get("errmsg", "未知错误")
        error_code = data.get("errcode", -1)
        logger.error("上传 newspic 素材图失败 [%d]: %s (文件: %s)", error_code, error_msg, image_path)
        raise RuntimeError(f"上传 newspic 素材图失败 [{error_code}]: {error_msg}")

    logger.info("贴图素材上传成功: media_id=%s (文件: %s)", data["media_id"], image_path.name)
    return data["media_id"]


def upload_content_image(image_path: Union[str, Path]) -> str:
    """
    上传文章正文图片(uploadimg 接口,不占永久素材配额)。

    返回 https:// 格式的 CDN URL(微信有时返回 http,这里统一改 https
    以避免草稿 HTML 里的混合内容阻拦)。
    """
    token = get_access_token()
    url = f"{API_BASE}/media/uploadimg?access_token={token}"

    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    mime_type = _guess_mime(image_path)

    with open(image_path, "rb") as f:
        files = {"media": (image_path.name, f, mime_type)}
        resp = _api_request_with_retry("POST", url, files=files)

    resp.raise_for_status()
    data = resp.json()

    if "url" not in data:
        error_msg = data.get("errmsg", "未知错误")
        error_code = data.get("errcode", -1)
        logger.error("上传正文图片失败 [%d]: %s (文件: %s)", error_code, error_msg, image_path)
        raise RuntimeError(f"上传正文图片失败 [{error_code}]: {error_msg}")

    img_url = data["url"]
    if img_url.startswith("http://"):
        img_url = "https://" + img_url[len("http://"):]
    logger.info("正文图片上传成功: %s (文件: %s)", img_url, image_path.name)
    return img_url


# ============================================================
# 草稿
# ============================================================

def add_newspic_draft(
    title: str,
    content: str,
    image_media_ids: List[str],
    author: str = "",
    need_open_comment: int = 0,
    only_fans_can_comment: int = 0,
) -> str:
    """
    新建"贴图"(图片消息)草稿。

    对应微信 `/cgi-bin/draft/add` 接口,`article_type = "newspic"`。
    和普通图文草稿的区别:
      - 没有 thumb_media_id,封面默认用 image_list[0]
      - 没有 HTML content,content 是一段纯文本短描述(100-300 字)
      - image_list 必须是已上传过的永久素材 media_id(用 `upload_newspic_image` 得到)

    Args:
        title: 标题(可选,微信允许空)
        content: 短描述文本(建议 100-300 字,太长不好看)
        image_media_ids: 5-20 张图的 media_id 列表,顺序即展示顺序,第 1 张是封面
        author: 作者名
        need_open_comment: 1 开启留言 / 0 关闭
        only_fans_can_comment: 1 只粉丝可留言 / 0 所有人

    Returns:
        草稿 media_id(字符串)
    """
    if not image_media_ids:
        raise ValueError("newspic 至少需要 1 张图")
    if len(image_media_ids) > 20:
        raise ValueError(f"newspic 最多 20 张图,当前 {len(image_media_ids)} 张")

    token = get_access_token()
    url = f"{API_BASE}/draft/add?access_token={token}"

    article: Dict[str, Any] = {
        "article_type": "newspic",
        "title": title,
        "content": content,
        "need_open_comment": need_open_comment,
        "only_fans_can_comment": only_fans_can_comment,
        "image_info": {
            "image_list": [{"image_media_id": mid} for mid in image_media_ids],
        },
    }
    if author:
        article["author"] = author

    payload = {"articles": [article]}

    resp = _api_request_with_retry(
        "POST", url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    resp.raise_for_status()
    data = resp.json()

    if "media_id" not in data:
        error_msg = data.get("errmsg", "未知错误")
        error_code = data.get("errcode", -1)
        logger.error("新建贴图草稿失败 [%d]: %s (标题: %s)", error_code, error_msg, title)
        raise RuntimeError(f"新建贴图草稿失败 [{error_code}]: {error_msg}")

    logger.info("贴图草稿创建成功: media_id=%s (标题: %s)", data["media_id"], title)
    return data["media_id"]


def add_draft(articles: Union[Dict[str, Any], List[Dict[str, Any]]]) -> str:
    """
    新建草稿。

    Args:
        articles: 单篇(dict)或多篇(list[dict])。每篇字典必选字段:
            - title, content (HTML), thumb_media_id
            可选: author, digest, content_source_url, need_open_comment, only_fans_can_comment

    Returns:
        str: 草稿 media_id
    """
    token = get_access_token()
    url = f"{API_BASE}/draft/add?access_token={token}"

    if isinstance(articles, dict):
        articles = [articles]

    payload = {"articles": articles}

    resp = _api_request_with_retry(
        "POST", url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    resp.raise_for_status()
    data = resp.json()

    if "media_id" not in data:
        error_msg = data.get("errmsg", "未知错误")
        error_code = data.get("errcode", -1)
        logger.error("新建草稿失败 [%d]: %s", error_code, error_msg)
        raise RuntimeError(f"新建草稿失败 [{error_code}]: {error_msg}")

    logger.info("草稿创建成功: media_id=%s", data["media_id"])
    return data["media_id"]


# ============================================================
# 获取草稿
# ============================================================

def get_draft(media_id: str) -> Dict[str, Any]:
    """
    通过 media_id 获取草稿详情，包含文章 URL。

    对应微信 `/cgi-bin/draft/get` 接口。
    返回的 url 是公众号文章链接（形如 https://mp.weixin.qq.com/s/...），
    用户可通过此链接在微信内预览或分享。

    Args:
        media_id: 草稿 media_id

    Returns:
        草稿详情字典，包含 title, url, thumb_url 等字段
    """
    token = get_access_token()
    url = f"{API_BASE}/draft/get?access_token={token}"

    payload = {"media_id": media_id}

    resp = _api_request_with_retry(
        "POST", url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    resp.raise_for_status()
    data = resp.json()

    if "news_item" not in data or not data["news_item"]:
        error_msg = data.get("errmsg", "未知错误")
        error_code = data.get("errcode", -1)
        logger.error("获取草稿失败 [%d]: %s (media_id=%s)", error_code, error_msg, media_id)
        raise RuntimeError(f"获取草稿失败 [{error_code}]: {error_msg}")

    item = data["news_item"][0]
    draft_url = item.get("url", "")
    title = item.get("title", "")

    logger.info(
        "草稿获取成功: media_id=%s url=%s",
        media_id, draft_url,
    )
    logger.info("  话题: %s", title)

    return {
        "media_id": media_id,
        "title": title,
        "url": draft_url,
        "thumb_url": item.get("thumb_url", ""),
        "author": item.get("author", ""),
        "digest": item.get("digest", ""),
        "content_source_url": item.get("content_source_url", ""),
        "raw": item,
    }


# ============================================================
# 草稿列表 / 删除草稿（draft/batchget & draft/delete）
# ============================================================

def get_draft_list(offset: int = 0, count: int = 20, no_content: int = 1) -> Dict[str, Any]:
    """
    获取草稿列表。

    对应微信 `/cgi-bin/draft/batchget` 接口。
    https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_batchget.html

    Args:
        offset: 偏移量（从全部草稿列表的该位置开始拉取）
        count: 拉取数量（1 ~ 20，默认 20）
        no_content: 1 表示不返回文章正文 content 字段

    Returns:
        {
            "item": [ { media_id, content: { news_item: [{title, author, digest,
                        content, url, thumb_url, ...}] }, update_time }, ... ],
            "total_count": int,
            "item_count": int
        }
    """
    token = get_access_token()
    url = f"{API_BASE}/draft/batchget?access_token={token}"

    count = max(1, min(20, count))
    payload = {"offset": offset, "count": count, "no_content": no_content}

    resp = _api_request_with_retry(
        "POST", url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    resp.raise_for_status()
    data = resp.json()

    if "item" not in data:
        error_msg = data.get("errmsg", "未知错误")
        error_code = data.get("errcode", -1)
        logger.error("获取草稿列表失败 [%d]: %s", error_code, error_msg)
        raise RuntimeError(f"获取草稿列表失败 [{error_code}]: {error_msg}")

    item_count = data.get("item_count", len(data["item"]))
    total_count = data.get("total_count", 0)
    logger.info("草稿列表获取成功: total=%d item_count=%d", total_count, item_count)
    return data


def delete_draft(media_id: str) -> Dict[str, Any]:
    """
    删除草稿。

    对应微信 `/cgi-bin/draft/delete` 接口。
    https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_delete.html

    Args:
        media_id: 草稿 media_id

    Returns:
        {"errcode": 0, "errmsg": "ok"}
    """
    token = get_access_token()
    url = f"{API_BASE}/draft/delete?access_token={token}"

    payload = {"media_id": media_id}

    resp = _api_request_with_retry(
        "POST", url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    resp.raise_for_status()
    data = resp.json()

    errcode = data.get("errcode", -1)
    if errcode != 0:
        error_msg = data.get("errmsg", "未知错误")
        logger.error("删除草稿失败 [%d]: %s (media_id=%s)", errcode, error_msg, media_id)
        raise RuntimeError(f"删除草稿失败 [{errcode}]: {error_msg}")

    logger.info("草稿删除成功: media_id=%s", media_id)
    return data


def update_draft(media_id: str, index: int, articles: Dict[str, Any]) -> Dict[str, Any]:
    """
    更新草稿。

    对应微信 `/cgi-bin/draft/update` 接口。
    https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_update.html

    Args:
        media_id: 草稿 media_id
        index: 要更新的文章在图文消息中的位置（0 表示第一篇）
        articles: 更新后的文章内容，必选字段: title, content
                  可选: author, digest, content_source_url, thumb_media_id,
                        show_cover_pic, need_open_comment, only_fans_can_comment

    Returns:
        {"errcode": 0, "errmsg": "ok"}
    """
    token = get_access_token()
    url = f"{API_BASE}/draft/update?access_token={token}"

    payload = {"media_id": media_id, "index": index, "articles": articles}

    resp = _api_request_with_retry(
        "POST", url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    resp.raise_for_status()
    data = resp.json()

    errcode = data.get("errcode", -1)
    if errcode != 0:
        error_msg = data.get("errmsg", "未知错误")
        logger.error("更新草稿失败 [%d]: %s (media_id=%s)", errcode, error_msg, media_id)
        raise RuntimeError(f"更新草稿失败 [{errcode}]: {error_msg}")

    logger.info("草稿更新成功: media_id=%s", media_id)
    return data


# ============================================================
# 永久素材管理（material/batchget_material & get_material & del_material）
# ============================================================

def get_material_list(material_type: str = "image", offset: int = 0, count: int = 20) -> Dict[str, Any]:
    """
    获取永久素材列表。

    对应微信 `/cgi-bin/material/batchget_material` 接口。
    https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_batchgetmaterial.html

    Args:
        material_type: 素材类型（image / video / voice / news）
        offset: 偏移量
        count: 拉取数量（1 ~ 20）

    Returns:
        {"total_count": int, "item_count": int, "item": [ {...} ]}
    """
    token = get_access_token()
    url = f"{API_BASE}/material/batchget_material?access_token={token}"

    count = max(1, min(20, count))
    payload = {"type": material_type, "offset": offset, "count": count}

    resp = _api_request_with_retry(
        "POST", url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    resp.raise_for_status()
    data = resp.json()

    if "errcode" in data and data["errcode"] != 0:
        error_msg = data.get("errmsg", "未知错误")
        error_code = data.get("errcode", -1)
        logger.error("获取素材列表失败 [%d]: %s", error_code, error_msg)
        raise RuntimeError(f"获取素材列表失败 [{error_code}]: {error_msg}")

    total_count = data.get("total_count", 0)
    item_count = data.get("item_count", 0)
    logger.info("素材列表获取成功: type=%s total=%d item_count=%d", material_type, total_count, item_count)
    return data


def get_material(media_id: str) -> Dict[str, Any]:
    """
    获取永久素材内容。

    对应微信 `/cgi-bin/material/get_material` 接口。
    https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_getmaterial.html

    注意：图片/语音/缩略图返回的是原始二进制，本函数返回 dict 格式，
    图片等二进制内容以 base64 编码放在 data 字段中。

    Args:
        media_id: 素材 media_id

    Returns:
        {
            "media_id": str,
            "type": "image"|"video"|"voice"|"news",
            "name": str,
            "url": str,           # 图片有 url
            "data": str,          # base64 编码的二进制内容（图片/语音）
            "update_time": int,
        }
    """
    token = get_access_token()
    url = f"{API_BASE}/material/get_material?access_token={token}"

    payload = {"media_id": media_id}

    resp = _api_request_with_retry(
        "POST", url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "application/json" in content_type or resp.text.strip().startswith("{"):
        # JSON 响应（图文 news / 视频 video / 或错误）
        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            error_msg = data.get("errmsg", "未知错误")
            error_code = data.get("errcode", -1)
            logger.error("获取素材失败 [%d]: %s (media_id=%s)", error_code, error_msg, media_id)
            raise RuntimeError(f"获取素材失败 [{error_code}]: {error_msg}")

        # 视频素材检测：微信可能返回两种格式
        # 格式1: {"title": "...", "description": "...", "down_url": "..."}
        # 格式2: {"news_item": [{"title": "...", "down_url": "...", ...}]}
        if "down_url" in data:
            logger.info("获取视频素材(格式1): media_id=%s", media_id)
            return {
                "media_id": media_id,
                "type": "video",
                "name": data.get("title", ""),
                "url": data.get("down_url", ""),
                "data": "",
                "content_type": "video/mp4",
                "down_url": data.get("down_url", ""),
                "description": data.get("description", ""),
                "update_time": data.get("update_time", 0),
            }

        news_item = data.get("news_item", [])
        if news_item and len(news_item) > 0 and "down_url" in news_item[0]:
            logger.info("获取视频素材(格式2-嵌套在news_item): media_id=%s", media_id)
            item = news_item[0]
            return {
                "media_id": media_id,
                "type": "video",
                "name": item.get("title", ""),
                "url": item.get("down_url", ""),
                "data": "",
                "content_type": "video/mp4",
                "down_url": item.get("down_url", ""),
                "description": item.get("description", ""),
                "update_time": data.get("update_time", 0),
            }

        # 图文素材
        return {
            "media_id": media_id,
            "type": "news",
            "name": news_item[0].get("title", "") if news_item else "",
            "url": news_item[0].get("url", "") if news_item else "",
            "data": "",
            "update_time": data.get("update_time", 0),
            "news_item": news_item,
        }
    else:
        # 二进制响应（图片/语音/缩略图），用 base64 编码返回
        import base64
        return {
            "media_id": media_id,
            "type": "image",
            "name": media_id,
            "url": "",
            "data": base64.b64encode(resp.content).decode("utf-8"),
            "content_type": content_type,
        }


def delete_material(media_id: str) -> Dict[str, Any]:
    """
    删除永久素材。

    对应微信 `/cgi-bin/material/del_material` 接口。
    https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_delmaterial.html

    Args:
        media_id: 素材 media_id

    Returns:
        {"errcode": 0, "errmsg": "ok"}
    """
    token = get_access_token()
    url = f"{API_BASE}/material/del_material?access_token={token}"

    payload = {"media_id": media_id}

    resp = _api_request_with_retry(
        "POST", url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    resp.raise_for_status()
    data = resp.json()

    errcode = data.get("errcode", -1)
    if errcode != 0:
        error_msg = data.get("errmsg", "未知错误")
        logger.error("删除素材失败 [%d]: %s (media_id=%s)", errcode, error_msg, media_id)
        raise RuntimeError(f"删除素材失败 [{errcode}]: {error_msg}")

    logger.info("素材删除成功: media_id=%s", media_id)
    return data


def upload_material(file_path: Union[str, Path], material_type: str = "image") -> Dict[str, Any]:
    """
    上传永久素材（image/voice/video/thumb）。

    对应微信 `/cgi-bin/material/add_material` 接口。
    https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_addmaterial.html

    对 image 类型，内部复用已有的 upload_thumb_image 逻辑。

    Args:
        file_path: 素材文件路径
        material_type: 素材类型（image / voice / video / thumb）

    Returns:
        {"media_id": str, "url": str (仅 image)}
    """
    if material_type == "image":
        media_id = upload_thumb_image(file_path)
        return {"media_id": media_id, "url": ""}

    # voice / video / thumb 需要独立上传
    token = get_access_token()
    url = f"{API_BASE}/material/add_material?access_token={token}&type={material_type}"

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"素材文件不存在: {file_path}")

    mime_type = _guess_mime(file_path)

    with open(file_path, "rb") as f:
        files: Dict[str, Any] = {"media": (file_path.name, f, mime_type)}
        if material_type == "video":
            # 视频需要额外的 description
            files["description"] = (None, json.dumps({"title": file_path.stem, "introduction": ""}, ensure_ascii=False))

        resp = _api_request_with_retry("POST", url, files=files)

    resp.raise_for_status()
    data = resp.json()

    if "media_id" not in data:
        error_msg = data.get("errmsg", "未知错误")
        error_code = data.get("errcode", -1)
        logger.error("上传素材失败 [%d]: %s (文件: %s)", error_code, error_msg, file_path)
        raise RuntimeError(f"上传素材失败 [{error_code}]: {error_msg}")

    logger.info("素材上传成功: media_id=%s type=%s (文件: %s)", data["media_id"], material_type, file_path.name)
    return {"media_id": data["media_id"], "url": data.get("url", "")}


# ============================================================
# 便捷函数
# ============================================================

def publish_article(
    title: str,
    html_content: str,
    cover_image_path: Union[str, Path],
    author: str = "",
    digest: str = "",
    source_url: str = "",
    account_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    一站式发布:上传封面图 → 创建草稿。

    Args:
        title: 文章标题
        html_content: 已排版的 HTML
        cover_image_path: 封面图路径
        author: 作者(空时从账号配置读)
        digest: 摘要(自动截 120 字)
        source_url: 原文链接
        account_name: 账号名(可选,默认用当前激活账号)

    Returns:
        {"media_id": str, "status": "success", "account": str}
    """
    if account_name:
        set_account(account_name)

    config = get_config(account_name)
    if not author:
        author = config.get("author", "")

    account_display = config.get("account_name", "default")
    logger.info("开始发布文章: %s → 账号: %s", title, account_display)
    logger.info("[1/2] 上传封面图...")
    thumb_media_id = upload_thumb_image(cover_image_path)

    logger.info("[2/2] 创建草稿...")
    article = {
        "title": title,
        "content": html_content,
        "thumb_media_id": thumb_media_id,
        "author": author,
        "digest": digest[:120] if digest else "",
    }
    if source_url:
        article["content_source_url"] = source_url

    media_id = add_draft(article)

    # 获取草稿 URL
    draft_info = get_draft(media_id)
    draft_url = draft_info["url"]

    logger.info(
        "发布成功! media_id=%s url=%s account=%s",
        media_id, draft_url, account_display,
    )
    logger.info("  话题: %s", title)

    return {
        "media_id": media_id,
        "cover_media_id": thumb_media_id,
        "url": draft_url,
        "status": "success",
        "account": account_display,
    }


def publish_newspic(
    title: str,
    content: str,
    image_paths: List[Union[str, Path]],
    author: str = "",
    account_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    一站式发布贴图(图片消息):
      1. 逐张上传为永久素材,收集 media_id
      2. 调用 draft/add 创建 newspic 草稿

    Args:
        title: 标题
        content: 短文本(100-300 字)
        image_paths: 图片本地路径列表,5-20 张。第 1 张作为封面。
        author: 作者名(空时从账号配置读)
        account_name: 账号名(可选,默认用当前激活账号)

    Returns:
        {"media_id": str, "status": "success", "account": str,
         "image_media_ids": list[str]}
    """
    if account_name:
        set_account(account_name)

    config = get_config(account_name)
    if not author:
        author = config.get("author", "")

    account_display = config.get("account_name", "default")
    logger.info("开始发布贴图: %s → 账号: %s 图片: %d 张", title or '(无标题)', account_display, len(image_paths))

    media_ids: List[str] = []
    for i, path in enumerate(image_paths, start=1):
        logger.info("[%d/%d] 上传第 %d 张...", i, len(image_paths), i)
        media_ids.append(upload_newspic_image(path))

    logger.info("创建贴图草稿...")
    draft_id = add_newspic_draft(
        title=title,
        content=content,
        image_media_ids=media_ids,
        author=author,
    )

    # 获取草稿 URL
    draft_info = get_draft(draft_id)
    draft_url = draft_info["url"]

    logger.info(
        "发布成功! media_id=%s url=%s account=%s",
        draft_id, draft_url, account_display,
    )
    logger.info("  话题: %s", title or '(无标题)')

    return {
        "media_id": draft_id,
        "url": draft_url,
        "status": "success",
        "account": account_display,
        "image_media_ids": media_ids,
    }
