"""Entity candidate collection.

Two sources, in this order: user-provided hints (canonical name + aliases +
type), then automatic discovery from speech attribution patterns. Hints win
because a real novel's cast list is cheaper and more accurate than any NER
pass we could run on a 500k-character text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import Chapter

_SPEECH = re.compile(
    r"(?P<name>[\u4e00-\u9fa5]{2,4})"
    r"(?:说道|问道|笑道|叹道|怒道|喝道|回答|开口|低声说|高声说|说|道|问|喊|叫)"
    r"[：:，,]?\s*[“\"]"
)
_STOPWORDS = {"他", "她", "它", "众人", "有人", "那人", "此人", "自己", "我们", "你们", "他们"}
_BAD_TAIL = set("回答说道问讲喊叫笑叹想看听站坐走来去声着了地的得边中里上下前后接反又大校耳眼手口身心脸头突然话")
_BAD_HEAD = set("他她它我你这也那又但可不没只就都还于是名位个条张把被给让向对在为而的着地得声后前指凑")
_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛"
    "奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康"
    "伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝"
    "闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解"
    "应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊惠甄曲封芮羿储靳汲邴糜松井段富"
    "巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟"
    "薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔胥苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍桑桂濮牛寿"
    "通边扈燕冀浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文"
    "寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚简饶曾沙鞠须巢关蒯相查荆红游竺权逯盖"
)
_TITLES = {"元首", "执政官", "统帅", "将军", "博士", "教授", "上校", "司令", "舰长", "队长", "政委", "长老"}
_FOREIGN_HEAD = set("伊阿奥托马约麦汤弗汉")
_COMMON_NOUNS = {
    "计算机", "方向", "时间", "问题", "世界", "宇宙", "人类", "地球", "太阳", "科学",
    "技术", "文明", "空间", "飞船", "舰队", "政府", "国家", "军队", "警察", "军官",
    "首长", "主任", "局长", "部长", "公司", "组织", "社会", "历史", "未来", "现在",
    "过去", "信息", "材料", "会议", "文件", "声音", "眼睛", "身体",
}
_PLACE_SUFFIX = ("山", "峰", "城", "殿", "宫", "府", "谷", "崖", "湖", "江", "关")
_ORG_SUFFIX = ("门", "派", "宗", "帮", "军", "阁", "盟", "会", "观", "寺")


@dataclass
class EntityCandidate:
    name: str
    type: str = "character"
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    mention_count: int = 0
    first_chapter: int = 0
    last_chapter: int = 0
    explicit_type: bool = False

    def surfaces(self) -> list[str]:
        return [surface for surface in [self.name, *self.aliases] if surface]


def collect_candidates(
    chapters: list[Chapter],
    *,
    hints: list[dict] | None = None,
) -> list[EntityCandidate]:
    candidates: dict[str, EntityCandidate] = {}

    for hint in hints or []:
        name = str(hint.get("name") or "").strip()
        if not name:
            continue
        candidates[name] = EntityCandidate(
            name=name,
            type=str(hint.get("type") or "character"),
            aliases=[str(a).strip() for a in hint.get("aliases", []) if str(a).strip()],
            description=str(hint.get("description") or ""),
            explicit_type=True,
        )

    known_surfaces = {
        surface
        for candidate in candidates.values()
        for surface in candidate.surfaces()
    }

    for chapter in chapters:
        for match in _SPEECH.finditer(chapter.text):
            name = match.group("name").strip()
            if name in _STOPWORDS or len(name) < 2:
                continue
            name = _clean_name(name)
            if not name:
                continue
            if name in known_surfaces:
                continue
            candidates.setdefault(name, EntityCandidate(name=name, type="character"))

    for candidate in candidates.values():
        surfaces = candidate.surfaces()
        count = 0
        first = last = None
        description = candidate.description
        for chapter in chapters:
            hits = sum(chapter.text.count(surface) for surface in surfaces)
            if hits:
                count += hits
                first = chapter.ordinal if first is None else min(first, chapter.ordinal)
                last = chapter.ordinal if last is None else max(last, chapter.ordinal)
                if not description:
                    description = _description(chapter.text, surfaces)
        candidate.mention_count = count
        candidate.first_chapter = first or 0
        candidate.last_chapter = last or 0
        candidate.description = description
        if not candidate.explicit_type and candidate.type == "character" and candidate.name.endswith(_PLACE_SUFFIX):
            candidate.type = "place"
        if not candidate.explicit_type and candidate.type == "character" and candidate.name.endswith(_ORG_SUFFIX):
            candidate.type = "org"

    return sorted(candidates.values(), key=lambda c: (-c.mention_count, c.name))


def _clean_name(name: str) -> str | None:
    """Trim attribution leftovers and reject names that cannot be a person."""
    while len(name) > 2 and name[0] in _BAD_HEAD:
        name = name[1:]
    while len(name) > 2 and name[-1] in _BAD_TAIL:
        name = name[:-1]
    if len(name) < 2 or name[0] in _BAD_HEAD or name[-1] in _BAD_TAIL:
        return None
    if name in _TITLES or name[0] in _SURNAMES or name[0] in _FOREIGN_HEAD:
        return None if name in _COMMON_NOUNS else name
    return None


def infer_place(text: str, candidates: list[EntityCandidate]) -> str:
    for candidate in candidates:
        if candidate.type == "place" and candidate.name in text:
            return candidate.name
    return ""


def _description(text: str, surfaces: list[str]) -> str:
    for sentence in re.split(r"(?<=[。！？])", text):
        if any(surface in sentence for surface in surfaces):
            return sentence.strip()[:60]
    return ""
