from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out = Path(r"D:\AgentCode\two\docs\assets")
out.mkdir(parents=True, exist_ok=True)
target = out / "ocr-sample.png"

image = Image.new("RGB", (900, 520), "#fbf8f1")
draw = ImageDraw.Draw(image)
draw.rectangle((36, 36, 864, 484), outline="#c9c0ae", width=2)
draw.rectangle((36, 36, 864, 108), fill="#17251f")
draw.text((64, 52), "RED COAST ARCHIVE / 档案摘录", font=ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 24), fill="#efe9dd")

font_title = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 38)
font_body = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 27)

draw.text((72, 150), "罗辑坐在窗前，外面下着细雨。", font=font_title, fill="#1b241f")
draw.text((72, 222), "他想起叶文洁说过的话：", font=font_body, fill="#1b241f")
draw.text((72, 278), "“要多想。”", font=font_body, fill="#1b241f")
draw.text((72, 354), "档案编号：ETO-1379    时期：危机纪元", font=font_body, fill="#6d756e")
draw.text((72, 410), "记录人：汪淼", font=font_body, fill="#6d756e")

image.save(target)
print(target)
