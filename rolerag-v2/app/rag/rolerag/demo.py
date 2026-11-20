"""Synthetic novel used by the offline demo and the end-to-end tests.

It is original text, six chapters, one causal chain: 拜师 -> 隐瞒 -> 逐出 ->
三年后 -> 断桥 -> 对峙 -> 原谅. Every character in it has an alias, a
public event, an org-mediated event and a private memory, so all five
visibility routes are exercised.
"""

from __future__ import annotations

from .build import BuildOutcome, build_all

SAMPLE_NOVEL = """第一章 拜师

青霄门在雪线之上。玄真道人收陆知微为徒那天，山门里落着细雨。

玄真道：“从今日起，你是我门下第七个弟子。”

陆知微跪下去，额头碰在青石上：“弟子记住了。”

沈砚站在廊下，替陆知微挡了半宿的风。苏晚笑他：“沈师兄，你倒是热心。”

沈砚道：“他年纪小。”

第二章 隐瞒

陆知微偷了丹房的药，被沈砚撞见。

沈砚隐瞒了陆知微偷药的事。

玄真逐沈砚下山。

苏晚道：“师父，沈师兄不是那样的人。”

玄真道：“他瞒我。”

陆知微站在门边，没有出声。

第三章 三年后

三年后，山下的雪化了又落。

苏晚下山采买，在渡口看见了沈砚。

苏晚告诉陆知微：“沈砚回来了。”

陆知微问：“他还认得路吗。”

苏晚道：“他不肯上山。”

第四章 雨夜

断桥那夜，雨很大。

沈砚斩赵七于桥头。

众人皆见，无人敢拦。

苏晚赶到时，只剩一把断剑。

第五章 对峙

玄真下山，在断桥边站了很久。

玄真辱沈砚：“你连门规都不认了。”

沈砚道：“我认过。”

苏晚道：“师父，回去吧。”

第六章 尾声

春天，青霄门重修了山门。

苏晚原谅沈砚。

陆知微问：“师姐，你为什么原谅他。”

苏晚道：“他救过你。”
"""

DEMO_HINTS = [
    {"name": "沈砚", "type": "character", "aliases": ["沈师兄", "砚儿"], "description": "青霄门大弟子，后被逐出山门"},
    {"name": "陆知微", "type": "character", "aliases": ["知微", "陆师弟"], "description": "青霄门最小的弟子"},
    {"name": "苏晚", "type": "character", "aliases": ["苏师姐"], "description": "青霄门二弟子"},
    {"name": "玄真", "type": "character", "aliases": ["师父", "玄真道人"], "description": "青霄门掌门"},
    {"name": "赵七", "type": "character", "aliases": ["赵师兄"], "description": "外门弟子"},
    {"name": "青霄门", "type": "org", "aliases": ["山门"], "description": "雪线之上的门派"},
    {"name": "断桥", "type": "place", "description": "山下渡口的断桥"},
]

DEMO_ORGS = {"青霄门": ["沈砚", "陆知微", "苏晚", "玄真", "赵七"]}

DEMO_QUESTIONS = [
    ("陆知微", 6, "你还记得沈砚被逐出山门那天吗"),
    ("陆知微", 6, "沈砚为什么斩了赵七"),
    ("陆知微", 6, "玄真辱沈砚那件事，你听说了吗"),
    ("陆知微", 6, "苏晚后来原谅沈砚了吗"),
    ("陆知微", 2, "沈砚为什么斩了赵七"),
    ("陆知微", 6, "你怎么看阿波罗登月"),
    ("玄真", 6, "你还记得沈砚隐瞒陆知微那件事吗"),
]


def build_demo(novel_id: str = "qingxiao") -> BuildOutcome:
    return build_all(
        SAMPLE_NOVEL,
        novel_id=novel_id,
        hints=DEMO_HINTS,
        org_members=DEMO_ORGS,
    )
