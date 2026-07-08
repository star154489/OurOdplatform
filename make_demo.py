"""造一个最小的、故意不平衡的 VOC 样例数据集,用于端到端测试。
不需要真实像素:转换器只从 XML 读 width/height 和框坐标,图像文件只用来做"图-标注配对"
检查,所以建空 .jpg 即可。故意让稀有类 `反光衣` 只占 12/62,为分层划分策略的演示埋伏笔。
"""
from pathlib import Path
import random

ROOT = Path("data/raw/demo")
IMG = ROOT / "images"
ANN = ROOT / "annotations"


def xml_for(stem, w, h, objects):
    objs = ""
    for name, (xmin, ymin, xmax, ymax) in objects:
        objs += (f"  <object>\n    <name>{name}</name>\n"
                 f"    <bndbox><xmin>{xmin}</xmin><ymin>{ymin}</ymin>"
                 f"<xmax>{xmax}</xmax><ymax>{ymax}</ymax></bndbox>\n  </object>\n")
    return (f"<annotation>\n  <filename>{stem}.jpg</filename>\n"
            f"  <size><width>{w}</width><height>{h}</height><depth>3</depth></size>\n{objs}</annotation>\n")


def main():
    random.seed(0)
    IMG.mkdir(parents=True, exist_ok=True)
    ANN.mkdir(parents=True, exist_ok=True)
    for i in range(50):
        stem = f"common_{i:03d}"
        objs = []
        for _ in range(random.randint(1, 3)):
            x = random.randint(0, 400)
            y = random.randint(0, 400)
            objs.append(("head", (x, y, x + 80, y + 80)))
        (ANN / f"{stem}.xml").write_text(xml_for(stem, 640, 480, objs), encoding="utf-8")
        (IMG / f"{stem}.jpg").write_bytes(b"")
    for i in range(12):
        stem = f"rare_{i:03d}"
        (ANN / f"{stem}.xml").write_text(
            xml_for(stem, 640, 480, [("反光衣", (100, 100, 260, 380)), ("head", (50, 50, 130, 130))]),
            encoding="utf-8")
        (IMG / f"{stem}.jpg").write_bytes(b"")
    print(f"生成完毕: {len(list(ANN.glob('*.xml')))} 个 xml, {len(list(IMG.glob('*.jpg')))} 张图 -> {ROOT}")


if __name__ == "__main__":
    main()
