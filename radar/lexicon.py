"""词库：把"判断力"集中在三个维度上

1. ENTITY      —— 谁（主体）。一个主体名出现在标题里，本身就意味着分量
2. EVENT_TYPE  —— 发生了什么（谓词）。裁定/罚款/制裁/收购 这类词与主体无关
3. SEVERITY    —— 烈度。用于中文，捕捉"战争/熔断"级别的极端事件

打分的关键不是"命中几个词"，而是 **主体 × 谓词 的组合**。
"宁德时代入股某公司"（主体 + 弱谓词）不该和"华为被判有罪"（主体 + 强谓词）同分。
"""

# ============ 主体词库 ============
# 命中即计 1 个主体，最多取 2 个（避免长文堆词虚高）
ENTITY = [
    # 中国核心资产 / 中概股（直接影响 A股、港股、ETF）
    "华为", "希音", "腾讯", "阿里", "京东", "拼多多", "网易", "百度",
    "比亚迪", "宁德时代", "中芯国际", "小米", "美团", "蔚来", "小鹏",
    "理想汽车", "药明康德", "长江存储", "大疆", "字节跳动", "寒武纪",
    "中际旭创", "工业富联", "贵州茅台", "万科", "恒大", "碧桂园",
    # 全球关键公司
    "英伟达", "台积电", "苹果", "特斯拉", "软银", "三星", "波音", "空客",
    "阿斯麦", "ARM", "英特尔", "高通", "美光", "OpenAI", "贝莱德",
    "高盛", "摩根士丹利", "桥水", "伯克希尔",
    # 监管与政策主体
    "央行", "人民银行", "证监会", "金融监管总局", "发改委", "财政部",
    "国常会", "中央政治局", "工信部", "商务部", "海关总署", "国资委",
    "外汇局", "能源局", "统计局",
    # 海外机构
    "美联储", "欧洲央行", "日本央行", "英国央行", "美国财政部", "白宫",
    "美国国会", "美国商务部", "SEC", "USTR", "FTC", "OPEC", "IMF",
    "世界银行", "BIS", "EIA", "IEA", "LME",
    # 交易所
    "上交所", "深交所", "北交所", "中金所", "上期所", "大商所", "郑商所",
    "广期所", "港交所", "芝商所", "纳斯达克", "纽交所",
    # 地缘主体
    "俄罗斯", "乌克兰", "普京", "泽连斯基", "伊朗", "以色列", "沙特",
    "胡塞", "哈马斯", "真主党", "朝鲜", "委内瑞拉", "土耳其", "印度",
    "欧盟", "北约", "红海", "霍尔木兹", "台海", "南海",
    "马六甲", "苏伊士运河", "巴拿马运河", "直布罗陀",
    "特朗普", "鲍威尔", "拜登", "内塔尼亚胡",
]

ENTITY_EN = [
    "huawei", "shein", "tencent", "alibaba", "jd.com", "pinduoduo", "baidu",
    "byd", "catl", "smic", "xiaomi", "meituan", "nio", "xpeng", "li auto",
    "nvda", "nvidia", "tsmc", "apple", "tesla", "softbank", "samsung",
    "boeing", "airbus", "asml", "intel", "qualcomm", "micron", "openai",
    "blackrock", "goldman", "morgan stanley", "berkshire",
    "pboc", "people's bank of china", "csrc", "ndrc", "mof", "state council",
    "federal reserve", "the fed", "ecb", "boj", "bank of japan", "bank of england",
    "treasury department", "white house", "congress", "commerce department",
    "sec ", "ustr", "ftc", "opec", "imf", "world bank", "bis", "eia", "iea", "lme",
    "shanghai stock exchange", "shenzhen stock exchange", "hkex", "cme", "nasdaq", "nyse",
    "russia", "putin", "ukraine", "zelensky", "iran", "israel", "saudi",
    "houthi", "hezbollah", "hamas", "north korea", "venezuela", "turkey", "india",
    "european union", "nato", "red sea", "hormuz", "taiwan", "south china sea",
    "trump", "powell", "netanyahu",
]

# ============ 事件类型词库（谓词）============
# 与主体无关，单独出现也说明"发生了实质事情"
EVENT_TYPE = [
    # 司法与监管处置
    "裁定", "判决", "裁决", "定罪", "罪名", "有罪", "认罪", "起诉", "公诉",
    "指控", "立案", "调查", "问询", "处罚", "罚款", "罚单", "和解", "赔偿",
    "冻结", "扣押", "查封", "传唤", "逮捕", "引渡",
    # 贸易与管制
    "制裁", "反制裁", "关税", "加征", "反倾销", "反补贴", "出口管制",
    "实体清单", "禁售", "禁令", "断供", "停供", "限制出口", "进口配额",
    # 资本运作
    "收购", "并购", "重组", "要约", "举牌", "增持", "减持", "回购",
    "分拆", "私有化", "借壳", "定增", "配股", "可转债", "强赎", "下修",
    "股权激励", "控制权变更", "重大合同", "中标",
    # 经营与风险
    "停牌", "复牌", "退市", "风险警示", "违约", "爆雷", "破产", "清算",
    "资金占用", "违规担保", "业绩预告", "预亏", "预增", "商誉减值",
    "停产", "检修", "减产", "增产", "涨价", "提价", "降价", "召回", "罢工",
    # 市场机制（期货与交易规则，对交易员是硬信号）
    "保证金", "涨跌停", "限仓", "交割", "强制减仓", "异常交易", "风险提示",
    "调整为", "手续费", "新合约", "上市交易", "熔断", "临时停牌",
    # 突发事件与航运（霍尔木兹/红海这类，对原油是直接冲击）
    "爆炸", "触雷", "遇袭", "遭袭", "起火", "沉没", "搁浅", "倾覆",
    "中断", "封锁", "断航", "滞留", "停航", "关闭海峡", "抛售", "抢购",
    # 债券与流动性
    "招标", "拍卖", "发行", "续发", "净投放", "净回笼", "逆回购", "MLF",
    "SLF", "降准", "降息", "加息", "LPR",
    # 港股 / 中概专用（内幕消息＝价格敏感公告）
    "内幕消息", "盈利警告", "盈利预喜", "短暂停牌", "复牌公告",
]

EVENT_TYPE_EN = [
    "convict", "verdict", "sentence", "guilty", "plead", "indict", "charge",
    "lawsuit", "sue", "probe", "investigat", "fine", "penalty", "settle",
    "sanction", "tariff", "antidumping", "export control", "entity list",
    "ban", "blacklist", "halt", "delist", "default", "bankrupt", "liquidation",
    "merger", "acquisition", "takeover", "buyout", "stake", "share sale",
    "downgrade", "upgrade", "recall", "strike", "shutdown", "outage",
    "production cut", "output cut", "price hike", "layoff",
    "margin requirement", "circuit breaker", "trading halt",
    "rate cut", "rate hike", "stimulus", "bailout",
    # 地缘与安全（原表缺失，导致"胡塞袭击沙特"拿不到谓词分）
    "attack", "attacks", "missile", "drone", "airstrike", "shelling",
    "invasion", "ceasefire", "escalation", "retaliat", "seize", "blockade",
    # 航运与突发（油轮遇袭、海峡封锁一类）
    "explosion", "explode", "mined", "sank", "blockade", "closure",
    "disrupt", "chokepoint", "strait", "tanker", "sell-off", "selloff",
    "plunge", "tumble", "surge", "rout", "freeze", "halted",
]

# ============ 司法定罪：比一般"调查"重一档 ============
# 美国法院给中国科技龙头定罪，通常紧跟制裁升级，对产业链是直接定价
CONVICTION = [
    "裁定", "判决", "裁决", "定罪", "罪名", "有罪", "认罪", "宣判",
]
CONVICTION_EN = [
    "convict", "guilty", "verdict", "sentence", "plead guilty", "indict",
]

# ============ 极端事件：只有这些才配叫醒你 ============
EXTREME = [
    "开战", "宣战", "战争爆发", "入侵", "政变", "军事打击",
    "熔断", "暂停交易", "暂停上市", "紧急降息", "紧急加息",
    "降准", "降息", "加息", "主权违约", "银行挤兑", "破产清算",
    "全面禁令", "断交", "核",
]
EXTREME_EN = [
    "declares war", "goes to war", "invasion", "coup", "circuit breaker",
    "trading halt", "emergency rate", "sovereign default", "bank run",
    "nuclear", "martial law",
]

# ============ 观点与访谈：不是事件，不该推 ============
# "某券商认为…" 是解释，不是事实。这类内容只进摘要，不进即时通道
OPINION = [
    "认为", "预计", "料将", "或将", "有望", "观点", "研报", "评论",
    "点评", "解读", "展望", "分析称", "表示", "指出", "预计将",
    "首席经济学家", "策略师", "分析师",
]
OPINION_EN = [
    "op-ed", "opinion", "commentary", "analysis", "interview",
    "explainer", "what to know", "column", "says", "expects",
    "forecasts", "sees ", "outlook", "preview", "take:", "view",
]

# ============ 烈度词：极端事件 ============
SEVERITY = [
    "战争", "开战", "空袭", "导弹", "无人机", "袭击", "入侵", "政变",
    "制裁", "禁运", "封锁", "断供", "出口管制", "实体清单",
    "降准", "降息", "加息", "紧急", "熔断", "暂停交易", "暂停上市",
    "暴跌", "暴涨", "闪崩", "违约", "爆雷", "破产", "挤兑",
    "立案", "处罚", "调查", "退市", "风险警示", "停牌",
    "关税", "反倾销", "断航", "停火", "谈判破裂",
]

# 交易所公告的实质内容词
SUBSTANTIVE = [
    "收购", "重组", "重大合同", "中标", "业绩预告", "业绩快报",
    "预亏", "预增", "立案", "处罚", "问询", "停牌", "复牌",
    "退市", "风险警示", "减持", "增持", "回购", "股权激励",
    "可转债", "下修", "强赎", "分红", "诉讼", "仲裁",
    "资金占用", "违规担保", "控制权变更", "要约收购", "分拆",
]

# 例行公告特征
ROUTINE = [
    "股东大会", "章程", "独立董事", "职工董事", "监事", "述职",
    "募集资金专户", "保荐", "持续督导", "会计师事务", "聘任",
    "辞职", "选举", "换届", "会议决议", "通知债权人",
]

# ============ 海外兜底：未命中主体/谓词时的行业词 ============
EN_CORE = [
    "federal reserve", "fed ", "rate cut", "rate hike", "interest rate",
    "tariff", "sanction", "export control", "stimulus", "reserve requirement",
    "pboc", "csrc", "opec", "output cut", "production cut", "war",
    "ceasefire", "escalation", "invasion", "election", "default",
    "downgrade", "bailout", "crash", "circuit breaker", "trading halt",
    "emergency", "inflation", "cpi", "ppi", "payroll", "jobless",
    "gdp", "recession", "devaluation",
]

EN_SECTOR = [
    "oil", "crude", "brent", "wti", "gold", "silver", "copper", "aluminum",
    "nickel", "lithium", "iron ore", "steel", "coal", "natural gas",
    "yuan", "renminbi", "dollar", "treasury yield", "china", "hang seng",
    "a-share", "shipping", "red sea", "semiconductor", "chip", "solar",
    "property developer", "rare earth",
]

EN_EXCLUDE = [
    "hurricane", "typhoon", "weather", "celebrity", "sports", "football",
    "basketball", "entertainment", "obituary", "recipe", "travel",
]


# ============ 判别物：标题里出现不同品种/主体，就不是同一件事 ============
# "黄金ETF持仓" vs "白银ETF持仓" 字面重合 79%，但显然是两条。
COMMODITY = [
    "黄金", "白银", "原油", "布伦特", "WTI", "铜", "铝", "锌", "镍", "铅",
    "锂", "碳酸锂", "铁矿石", "螺纹钢", "热卷", "焦煤", "焦炭", "动力煤",
    "豆粕", "豆油", "棕榈油", "菜粕", "橡胶", "PTA", "甲醇", "乙二醇",
    "生猪", "玉米", "白糖", "棉花", "玻璃", "纯碱", "工业硅", "多晶硅",
    "天然气", "燃油", "沥青", "纸浆", "沪金", "沪银", "沪铜", "沪镍",
]


def distinctive(text, text_low=None):
    """返回该标题的判别物集合：主体 + 商品品种（已做同义归一）。"""
    text_low = text_low if text_low is not None else text.lower()
    comm = {COMMODITY_ALIAS.get(w, w) for w in COMMODITY if w in text}
    return set(entities(text, text_low)) | comm


# ============ 同义词归一：缩写与全称必须视为同一个词 ============
# "美国FTC" 与 "美国联邦贸易委员会" 是同一机构，不归一则永远聚不到一起
SYNONYM = {
    "ftc": "联邦贸易委员会",
    "sec": "证券交易委员会",
    "sec.": "证券交易委员会",
    "the fed": "美联储",
    "fed": "美联储",
    "federal reserve": "美联储",
    "pboc": "中国人民银行",
    "people's bank of china": "中国人民银行",
    "csrc": "证监会",
    "opec": "欧佩克",
    "imf": "国际货币基金组织",
    "ecb": "欧洲央行",
    "boj": "日本央行",
    "bank of japan": "日本央行",
    "ustr": "美国贸易代表办公室",
    "eia": "美国能源信息署",
    "iea": "国际能源署",
    "lme": "伦敦金属交易所",
    "ipo": "首次公开发行",
    "etf": "交易所交易基金",
    # 中文侧的口语简称
    "恒指": "恒生指数",
    "沪指": "上证指数",
    "创指": "创业板指",
    "期指": "股指期货",
    "美联储局": "美联储",
}

# 判别物同义：避免"沪金"与"黄金"、"原油"与"布伦特"被当成不同品种
COMMODITY_ALIAS = {
    "沪金": "黄金", "沪银": "白银", "沪铜": "铜", "沪铝": "铝", "沪镍": "镍",
    "布伦特": "原油", "WTI": "原油", "WTI原油": "原油", "美原油": "原油",
}


def hits(text, words):
    """命中计数（子串匹配）"""
    return sum(1 for w in words if w and w in text)


def entities(text, text_low):
    """返回命中的主体列表（去重）。中英文各扫一遍。"""
    found = [w for w in ENTITY if w in text]
    found += [w for w in ENTITY_EN if w in text_low]
    return found
