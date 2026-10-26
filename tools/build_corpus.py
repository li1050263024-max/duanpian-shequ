# -*- coding: utf-8 -*-
"""从 lofter_hot_500.jsonl 提取每篇的情节标签和关键词，写成 data/corpus.js。"""
import json
import re
from collections import Counter, defaultdict

import jieba
import jieba.analyse

jieba.setLogLevel(20)

SRC = r"C:\Users\ihuab\Desktop\lofter_hot_500.jsonl"
OUT = r"D:\新建文件夹\短篇社区\data\corpus.js"

# (标准名, 分类, 匹配词, 范围) 范围 header=只看标题和开头标注, any=全文
LEXICON = [
    ("追妻火葬场", "plot", ["追妻火葬场", "追妻火葬"], "any"),
    ("破镜重圆", "plot", ["破镜重圆", "破镜", "重归于好"], "any"),
    ("先婚后爱", "plot", ["先婚后爱"], "any"),
    ("带球跑", "plot", ["带球跑", "带球", "未婚先孕"], "any"),
    ("替身", "plot", ["替身"], "any"),
    ("白月光", "plot", ["白月光"], "any"),
    ("双向暗恋", "plot", ["双向暗恋"], "any"),
    ("暗恋", "plot", ["暗恋"], "any"),
    ("青梅竹马", "plot", ["青梅竹马", "青梅竹马", "两小无猜"], "any"),
    ("久别重逢", "plot", ["久别重逢", "多年后重逢"], "any"),
    ("联姻", "plot", ["联姻", "商业联姻", "家族联姻", "契约婚姻", "协议结婚"], "any"),
    ("闪婚", "plot", ["闪婚"], "any"),
    ("隐婚", "plot", ["隐婚"], "any"),
    ("离婚拉扯", "plot", ["离婚"], "any"),
    ("复婚", "plot", ["复婚"], "any"),
    ("冷战", "plot", ["冷战"], "any"),
    ("海王回头", "plot", ["海王"], "any"),
    ("修罗场", "plot", ["修罗场"], "any"),
    ("一见钟情", "plot", ["一见钟情"], "any"),
    ("先虐后甜", "plot", ["先虐后甜"], "any"),
    ("失忆", "plot", ["失忆"], "any"),
    ("救赎", "plot", ["救赎"], "any"),
    ("女追男", "plot", ["女追男", "反追"], "any"),
    ("双向奔赴", "plot", ["双向奔赴"], "any"),
    ("误会", "plot", ["误会"], "header"),
    ("求婚", "plot", ["求婚"], "header"),
    ("霸总", "persona", ["霸总", "霸道总裁"], "any"),
    ("禁欲", "persona", ["禁欲"], "any"),
    ("腹黑", "persona", ["腹黑"], "any"),
    ("白切黑", "persona", ["白切黑"], "any"),
    ("傲娇", "persona", ["傲娇"], "any"),
    ("忠犬", "persona", ["忠犬"], "any"),
    ("奶狗", "persona", ["奶狗"], "any"),
    ("冰山", "persona", ["冰山", "不食人间烟火"], "header"),
    ("小太阳", "persona", ["小太阳"], "any"),
    ("社畜", "persona", ["社畜"], "any"),
    ("嘴硬心软", "persona", ["嘴硬"], "any"),
    ("占有欲", "persona", ["占有欲"], "any"),
    ("女强", "persona", ["女强"], "any"),
    ("前任", "relation", ["前任"], "any"),
    ("学长", "relation", ["学长"], "any"),
    ("年下", "relation", ["年下", "姐弟"], "any"),
    ("年上", "relation", ["年上"], "any"),
    ("助理", "relation", ["助理", "经纪人"], "any"),
    ("邻居", "relation", ["邻居", "合租"], "any"),
    ("校园", "setting", ["校园", "大学", "高校"], "any"),
    ("高中回忆", "setting", ["高中"], "header"),
    ("娱乐圈", "setting", ["娱乐圈", "顶流", "爱豆", "练习生"], "any"),
    ("豪门", "setting", ["豪门"], "any"),
    ("医院", "setting", ["医生", "医院", "病房"], "any"),
    ("公司", "setting", ["公司", "职场", "办公室"], "header"),
    ("机场", "setting", ["机场"], "any"),
    ("雨夜", "setting", ["雨夜", "下雨", "雨中"], "header"),
    ("雪天", "setting", ["雪天", "下雪", "雪里"], "header"),
    ("婚礼", "setting", ["婚礼", "结婚典礼"], "any"),
    ("酒店", "setting", ["酒店"], "header"),
    ("家乡", "setting", ["回老家", "家乡", "老家"], "header"),
    ("甜", "mood", ["甜文", "甜饼", "高甜", "小甜饼"], "header"),
    ("虐", "mood", ["虐文", "酸虐", "致郁"], "header"),
    ("治愈", "mood", ["治愈"], "any"),
    ("沙雕", "mood", ["沙雕", "搞笑", "轻松"], "header"),
    ("酸涩", "mood", ["酸涩"], "any"),
    ("短打", "craft", ["短打"], "header"),
    ("第二人称", "craft", ["第二人称"], "header"),
]

REAL_NAMES = ["马嘉祺", "严浩翔", "刘耀文", "宋亚轩", "丁程鑫", "贺峻霖", "张真源"]
NICK_NAMES = ["马哥", "翔哥", "文哥", "轩哥", "鑫哥", "霖哥", "祺哥", "时代少年团"]
NAMES = REAL_NAMES + NICK_NAMES
# 只在正文里偶尔出现就不要打上的标签，开头标注命中则不受此限制
BODY_MIN = {
    "校园": 3, "医院": 2, "婚礼": 2, "助理": 4, "邻居": 2, "机场": 2,
    "前任": 2, "学长": 2, "暗恋": 2, "联姻": 2, "年下": 2, "年上": 2,
    "娱乐圈": 2, "豪门": 1, "冷战": 1, "替身": 1, "白月光": 1,
}
CP_MAP = {
    "祺": "马嘉祺",
    "翔": "严浩翔",
    "文": "刘耀文",
    "轩": "宋亚轩",
    "真": "张真源",
    "鑫": "丁程鑫",
    "霖": "贺峻霖",
}
STOP = set("""
一个 自己 我们 什么 没有 知道 就是 这个 不是 因为 所以 如果 还是 已经 开始 时候 觉得 可以
这样 然后 但是 他们 她们 以及 现在 以后 之前 一个 一下 一点 一直 不会 不能 怎么 为什么
今天 明天 昨天 晚上 早上 心里 眼睛 声音 样子 地方 东西 事情 时候 感觉 发现 看到 看着
过来 过去 出来 进去 下来 起来 回去 知道 觉得 希望 已经 还是 只是 真的 突然 终于 原来
女人 男人 女孩 男孩 女生 男生 姑娘 少年 先生 小姐 老婆 老公 宝贝 乖乖 对方 别人 大家
手机 电话 微信 消息 照片 时间 日子 生活 世界 人间 最后 其实 当然 虽然 可是 于是 然后
自己 他们 她们 它们 什么 怎么 这个 那个 这里 那里 一种 一些 一切 一起 一直 一定
全文 上升 真人 生贺 联文 彩蛋 正文 推荐 字数 左右 关于 一个 没有 不是
喜欢 爱你 爱人 爱情 分手 复合 结婚 故事 小说 短篇 文章
""".split())
STOP.update(NAMES)
STOP.update("""男主 女主 时候 样子 地方 房间 女朋友 前女友 前男友 同学 朋友 妈妈 爸爸 母亲 父亲
语气 口气 神色 表情 眼神 声音 动作 开口 抬头 低头 点头 摇头 立马 用力 下唇 嘴唇 嘴巴 手指 头发
外套 衬衫 衣服 眼泪 泪水 呼吸 心跳 耳根 脸红 门口 身边 面前 心里 眼里 手里 身上 后来 刚刚
宝贝 乖乖 老公 老婆 姑娘 少年 先生 小姐 手机 微信 电话 照片 日子 生活 事情 东西 感觉
发现 告诉 继续 开始 结束 好像 似乎 仿佛 有些 整个 所有 自己 朋友 同学 学校
内心 皱眉 床上 眼眶 心情 温度 视线 脖子 腰间 怀里 胳膊 手腕 酒窝 马尾 裙子 高跟鞋 沙发 酒店 晚上 夜里
嫂子 姐夫 小叔 叔叔 舅舅 哥哥 弟弟 姐姐 妹妹 妈咪 亲哥 爸爸 妈妈 父母
""".split())

SEX_RE = re.compile(r"做爱|上床|插入|高潮|裸体|裸着|色情|性交|破处|肉棒|开房|内射|口交|腿软|喘|舌尖|胸口|欲望")
MINOR_RE = re.compile(r"未成年|未满十八|高中生|初中生|高一|高二|高三|初一|初二|初三|(?:1[0-7]|十[一二三四五六七])岁")
INCEST_RE = re.compile(r"骨科|乱伦|亲兄妹|亲哥哥|亲弟弟|同父异母|同母异父")
HE_RE = re.compile(r"(?<![A-Za-z])HE(?![A-Za-z])", re.I)
BE_RE = re.compile(r"(?<![A-Za-z])BE(?![A-Za-z])", re.I)
QUOTE_RE = re.compile(r"[“\"]([^”\"\n]{6,36})[”\"]")


def split_zones(title, content):
    lines = content.splitlines()
    pre = []
    start = 0
    for i, line in enumerate(lines[:36]):
        s = line.strip()
        if re.fullmatch(r"[0-9]{1,2}|0\d|[0-9]+[\.、]|正文|[-—]{2,}", s or ""):
            start = i + 1
            break
        if len(s) > 80 and not s.startswith(("*", "-", "—", "｜", "|", "「")):
            start = i
            break
        pre.append(s)
    else:
        start = min(8, len(lines))
    header = title + "\n" + "\n".join(pre)
    body = "\n".join(lines[start:])
    return header, body, pre


def clean_note(s):
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"[@＠]\S+", "", s)
    s = s.strip().strip("*-—#｜| ")
    if not s or len(s) > 24 or len(s) < 2:
        return ""
    if re.search(r"勿上升|全文|字数|bgm|BGM|生贺|联文|上一棒|下一棒|推荐|送给", s, re.I):
        return ""
    return s


def hit(text, word):
    if word == "暗恋":
        return re.search(r"(?<!双向)暗恋", text) is not None
    return word in text


def has_any(text, words):
    return any(hit(text, w) for w in words)


def detect_block(text):
    if INCEST_RE.search(text):
        return "含亲属恋情，不进入生成"
    for m in MINOR_RE.finditer(text):
        a = max(0, m.start() - 100)
        b = min(len(text), m.end() + 100)
        if SEX_RE.search(text[a:b]):
            return "含未成年相关的性描写，不进入生成"
    return ""


def redact(text):
    for n in sorted(NAMES, key=len, reverse=True):
        text = text.replace(n, "男主")
    return text


def safe_excerpt(body):
    chunks = []
    for line in body.splitlines():
        s = line.strip()
        if not s or len(s) < 18:
            continue
        if s.startswith(("*", "-", "—", "｜", "|")):
            continue
        if SEX_RE.search(s) or MINOR_RE.search(s) or re.search(r"吻|床|裸|喘|舌|腰|欲|第一次|昨晚|清白", s):
            continue
        s = redact(s).replace("//", "")
        s = re.sub(r"\s+", "", s)
        chunks.append(s)
        if sum(len(x) for x in chunks) > 80:
            break
    text = "".join(chunks)
    if len(text) > 80:
        text = text[:80] + "…"
    return text


def safe_hook(header, body):
    for zone in (header, body[:700]):
        for m in QUOTE_RE.finditer(zone):
            q = m.group(1).strip()
            if SEX_RE.search(q) or MINOR_RE.search(q):
                continue
            if any(n in q for n in NAMES):
                q = redact(q)
            if "男主" in q and len(q) < 10:
                continue
            return q
    return ""


def source_people(title, text):
    found = [n for n in REAL_NAMES if n in (title + "\n" + text[:1500])]
    m = re.search(r"[【\[「]?([祺翔文轩真鑫霖])我", title)
    if m:
        person = CP_MAP.get(m.group(1))
        if person and person not in found:
            found.insert(0, person)
    return found[:3]


def extract_keywords(text):
    text = redact(text)
    words = jieba.analyse.extract_tags(
        text[:8000], topK=30, withWeight=False, allowPOS=("n", "nz", "ns", "vn", "an")
    )
    kept = []
    for w in words:
        if len(w) < 2 or w in STOP:
            continue
        if w in NAMES or any(n in w for n in NAMES):
            continue
        if re.fullmatch(r"[\dA-Za-z]+", w):
            continue
        if w in {item[0] for item in LEXICON}:
            continue
        kept.append(w)
        if len(kept) >= 8:
            break
    return kept


def tag_story(title, content):
    header, body, pre_lines = split_zones(title, content)
    notes = []
    for line in pre_lines:
        note = clean_note(line)
        if note and SEX_RE.search(note):
            continue
        note = redact(note) if note else ""
        if note and note not in notes:
            notes.append(note)
    grouped = defaultdict(list)
    header_hit = set()
    for name, cat, words, scope in LEXICON:
        in_header = has_any(header, words)
        body_count = sum(body.count(w) for w in words if w != "暗恋")
        if "暗恋" in words:
            body_count += len(re.findall(r"(?<!双向)暗恋", body))
        need = BODY_MIN.get(name, 1)
        in_body = scope == "any" and body_count >= need
        if name == "追妻火葬场" and "追妻" in header + body and "火葬" in header + body:
            in_header = in_header or ("追妻" in header or "火葬" in header)
            in_body = True
        if name == "暗恋" and "双向暗恋" in header:
            in_header = has_any(header, ["暗恋"]) and "双向暗恋" not in header
        if not in_header and not in_body:
            continue
        if name not in grouped[cat]:
            grouped[cat].append(name)
        if in_header:
            header_hit.add(name)
    # 标题或开头里的甜 / 虐 / 雨 / 雪，用更短的词再补一次
    if re.search(r"甜", title) or any("甜" in n for n in notes):
        if "甜" not in grouped["mood"]:
            grouped["mood"].append("甜")
    if re.search(r"虐", title) or any("虐" in n for n in notes):
        if "虐" not in grouped["mood"]:
            grouped["mood"].append("虐")
    if "雨" in title or any("雨" in n for n in notes):
        if "雨夜" not in grouped["setting"]:
            grouped["setting"].append("雨夜")
    if "雪" in title or any("雪" in n for n in notes):
        if "雪天" not in grouped["setting"]:
            grouped["setting"].append("雪天")
    if re.search(r"[祺翔文轩真鑫霖]你|[×xX/／]你|第二人称", title) or title.strip().endswith("你"):
        if "第二人称" not in grouped["craft"]:
            grouped["craft"].append("第二人称")
    if "第二人称" not in grouped["craft"]:
        grouped["craft"].append("第一人称")
    if HE_RE.search(header):
        grouped["mood"].append("HE")
    if BE_RE.search(header):
        grouped["mood"].append("BE")
    # 开头命中的标签排在前面，每类最多 4 个
    for cat in list(grouped):
        uniq = []
        for n in grouped[cat]:
            if n not in uniq:
                uniq.append(n)
        order = {n: i for i, n in enumerate(uniq)}
        uniq.sort(key=lambda n: (n not in header_hit, order[n]))
        grouped[cat] = uniq[:4]
    return grouped, notes[:4]


def ending_of(mood):
    if "BE" in mood:
        return "BE"
    return "HE"


def main():
    stories = []
    blocked = 0
    with open(SRC, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            title = (obj.get("title") or "").strip() or "无题"
            content = obj.get("content") or ""
            grouped, notes = tag_story(title, content)
            reason = detect_block(content)
            if reason:
                blocked += 1
            people = source_people(title, content)
            item = {
                "id": str(obj.get("post_id") or ""),
                "title": title,
                "author": (obj.get("author") or "").strip(),
                "hot": int(obj.get("hot") or 0),
                "comments": int(obj.get("comments") or 0),
                "chars": len(content),
                "url": obj.get("url") or "",
                "people": people,
                "notes": notes,
                "tags": {
                    "plot": grouped.get("plot", []),
                    "persona": grouped.get("persona", []),
                    "relation": grouped.get("relation", []),
                    "setting": grouped.get("setting", []),
                    "mood": grouped.get("mood", []),
                    "craft": grouped.get("craft", []),
                },
                "keywords": [] if reason else extract_keywords(title + "\n" + content),
                "hook": "" if reason else safe_hook(title, content),
                "excerpt": "" if reason else safe_excerpt(content),
                "content": "" if reason else content,
                "ending": ending_of(grouped.get("mood", [])),
                "blocked": bool(reason),
                "blockReason": reason,
            }
            stories.append(item)
    stories.sort(key=lambda s: s["hot"], reverse=True)
    stats = {}
    for key in ("plot", "persona", "relation", "setting", "mood", "craft"):
        c = Counter()
        for s in stories:
            c.update(s["tags"].get(key) or [])
        stats[key] = c.most_common(18)
    payload = {
        "source": "lofter_hot_500.jsonl",
        "count": len(stories),
        "blocked": blocked,
        "stats": stats,
        "stories": stories,
    }
    with open(OUT, "w", encoding="utf-8") as wf:
        wf.write("window.CORPUS = ")
        json.dump(payload, wf, ensure_ascii=False, separators=(",", ":"))
        wf.write(";\n")
    print(json.dumps({
        "count": len(stories),
        "blocked": blocked,
        "plot": stats["plot"][:12],
        "with_keywords": sum(1 for s in stories if s["keywords"]),
        "with_excerpt": sum(1 for s in stories if s["excerpt"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
