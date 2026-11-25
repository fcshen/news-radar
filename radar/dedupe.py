"""去重与聚类：URL 规范化 → 精确指纹 → 标题相似度 → SimHash 兜底

关键改动：不再只比"标题前 14 个字"。
同一件事在不同媒体手里，措辞几乎必然不同（"FTC 订立协议" vs "联邦贸易委员会的协议"），
所以改成 **标题字符二元组的包含度 + 主体交集** 双条件判定：
  - 包含度够高（≥0.55）：字面高度重合，直接并
  - 主体有交集 且 包含度中等（≥0.40）：同一主体 + 措辞相近，并
这样既不漏并，也不会因为都提"美国财政部"就把两件事并成一件事。
"""
import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from . import lexicon as lx

TRACKING = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "spm", "from", "share", "ref", "fbclid", "gclid", "yclid", "scene",
}

# 聚类阈值
CONT_STRICT = 0.50      # 字面高度重合
CONT_LOOSE = 0.40       # 有共同主体时的放宽线

# 标题里对判定无贡献的字（虚词与来源标点）
_NOISE = set("的一是在了与和及对为以于从到被把就都也还很更最将会可能已经今日昨日"
             "据报道消息称记者编辑来源原标题讯电")


def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
             if k.lower() not in TRACKING]
    path = p.path.rstrip("/") or "/"
    scheme = "https" if p.scheme in ("http", "https") else p.scheme
    return urlunparse((scheme, p.netloc.lower(), path,
                       p.params, urlencode(query), ""))


def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fingerprint(title: str, body: str = "") -> str:
    key = clean_text(title)[:120] + "|" + clean_text(body)[:80]
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def _tokens(text: str):
    """中文按字 bigram，英文按词，混排都能处理。"""
    text = clean_text(text).lower()
    words = re.findall(r"[a-z0-9]+", text)
    zh = re.sub(r"[^\u4e00-\u9fff]", "", text)
    grams = [zh[i:i + 2] for i in range(len(zh) - 1)]
    return words + grams


def simhash(text: str, bits: int = 64) -> int:
    vec = [0] * bits
    for tok in _tokens(text):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(bits):
            vec[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(bits):
        if vec[i] > 0:
            out |= (1 << i)
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ---------------- 标题相似度（聚类主判据） ----------------

def normalize_synonyms(text: str) -> str:
    """把缩写与全称、口语简称与正式名统一，否则同一件事永远聚不到一起。"""
    out = text
    # 先长后短，避免 "the fed" 被 "fed" 抢先替换后留下 "the 美联储"
    for k in sorted(lx.SYNONYM, key=len, reverse=True):
        v = lx.SYNONYM[k]
        if k.isascii():
            out = re.sub(rf"(?<![a-z]){re.escape(k)}(?![a-z])", v, out, flags=re.I)
        else:
            out = out.replace(k, v)
    return out


def title_grams(title: str):
    """标题的中文字二元组集合 + 英文词集合，已剔除虚词与标点。"""
    t = normalize_synonyms(clean_text(title)).lower()
    # 去掉来源前缀与括号注记
    t = re.sub(r"[（(【\[].*?[)）】\]]", " ", t)
    zh = re.sub(r"[^\u4e00-\u9fff]", "", t)
    zh = "".join(ch for ch in zh if ch not in _NOISE)
    grams = {zh[i:i + 2] for i in range(len(zh) - 1)}
    words = {w for w in re.findall(r"[a-z0-9]{2,}", t)}
    return grams | words


def containment(a_grams, b_grams) -> float:
    """包含度：交集 / 较短一方。用于"短标题是长标题的子集"这种常见情形。"""
    if not a_grams or not b_grams:
        return 0.0
    inter = len(a_grams & b_grams)
    return inter / min(len(a_grams), len(b_grams))


def same_event(title_a: str, title_b: str) -> bool:
    # 判别物完全不相交（黄金 vs 白银、华为 vs 小米），一定不是同一件事。
    # 注意：只在两边都非空时才否决，"美国财政部"与"财政部"这类上下位关系不能误伤。
    da = lx.distinctive(title_a)
    db = lx.distinctive(title_b)
    if da and db and not (da & db):
        return False

    ga, gb = title_grams(title_a), title_grams(title_b)
    cont = containment(ga, gb)
    if cont >= CONT_STRICT:
        return True
    if cont >= CONT_LOOSE and (da & db):
        return True
    return False


def find_cluster(candidate_hash: int, pool, threshold: int = 3):
    """旧接口：按 SimHash 找簇。pool: [(cluster_id, simhash_int)]"""
    for cid, h in pool:
        if hamming(candidate_hash, h) <= threshold:
            return cid
    return None


def find_cluster_by_title(title: str, pool):
    """按标题相似度找簇。pool: [(cluster_id, simhash_int, title)]

    同一簇里的标题可能越滚越长，所以与簇内**每个**标题比一次。
    """
    for cid, _sh, t in pool:
        if t and same_event(title, t):
            return cid
    return None
