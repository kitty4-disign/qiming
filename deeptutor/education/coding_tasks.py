"""K12 coding tasks (M3 §8.1).

A small in-repo fixture of auditable coding tasks. The first flagship task
serves the high-school course: extract features from a 2D array and classify
with a nearest-centroid rule. No network downloads — data is inline.
"""

from __future__ import annotations

from deeptutor.education.coding_models import CodingTask, TestCase
from deeptutor.education.models import EducationStage

_HIGH_IMAGE_FEATURES_TASK = CodingTask(
    id="image-features-nearest-centroid",
    course_id="python-image-classifier",
    stage=EducationStage.HIGH,
    title="用二维数组提取图像特征并完成二分类",
    instructions=(
        "你将实现一个极简的图像分类器。\n"
        "1. 把一张 3x3 的灰度图看作二维数组，计算它的行均值作为特征向量（长度为 3）。\n"
        "2. 给定两个类别的质心 A=[0.2, 0.2, 0.2] 和 B=[0.8, 0.8, 0.8]。\n"
        "3. 找到距离特征向量最近的质心，输出 A 或 B。\n"
        "距离使用欧氏距离。注意：不要使用任何外部库，仅用 Python 标准库。\n"
        "输入格式：三行，每行三个 0-1 之间的浮点数，表示一张 3x3 图像。\n"
        "输出格式：单个字母 A 或 B。"
    ),
    starter_code=(
        "import sys\n"
        "import math\n"
        "\n"
        "def read_image():\n"
        "    rows = []\n"
        "    for _ in range(3):\n"
        "        line = sys.stdin.readline()\n"
        "        rows.append([float(x) for x in line.strip().split()])\n"
        "    return rows\n"
        "\n"
        "def extract_features(image):\n"
        "    # TODO: 计算每一行的均值，返回长度为 3 的列表\n"
        "    return [0.0, 0.0, 0.0]\n"
        "\n"
        "def nearest_centroid(features, centroids):\n"
        "    # TODO: 返回距离最近的质心标签（'A' 或 'B'）\n"
        "    return 'A'\n"
        "\n"
        "def main():\n"
        "    image = read_image()\n"
        "    features = extract_features(image)\n"
        "    centroids = {'A': [0.2, 0.2, 0.2], 'B': [0.8, 0.8, 0.8]}\n"
        "    label = nearest_centroid(features, centroids)\n"
        "    print(label)\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    ),
    allowed_languages=["python"],
    visible_tests=[
        TestCase(
            name="浅色图归入A",
            stdin="0.1 0.2 0.1\n0.2 0.1 0.2\n0.1 0.1 0.2\n",
            expected_stdout="A\n",
        ),
        TestCase(
            name="深色图归入B",
            stdin="0.9 0.8 0.9\n0.8 0.9 0.8\n0.9 0.8 0.9\n",
            expected_stdout="B\n",
        ),
    ],
    hidden_tests=[
        TestCase(
            name="边界图归入A",
            stdin="0.3 0.3 0.3\n0.3 0.3 0.3\n0.3 0.3 0.3\n",
            expected_stdout="A\n",
            is_hidden=True,
        ),
        TestCase(
            name="边界图归入B",
            stdin="0.6 0.6 0.6\n0.6 0.6 0.6\n0.6 0.6 0.6\n",
            expected_stdout="B\n",
            is_hidden=True,
        ),
    ],
    hints=[
        "行均值 = 对每行的三个数求和再除以 3。",
        "欧氏距离 = sqrt(sum((f-c)**2))，对两个质心都算一遍取较小者。",
        "注意 read_image 读取的是字符串，需要 float() 转换。",
    ],
)

_TASKS: dict[str, CodingTask] = {_HIGH_IMAGE_FEATURES_TASK.id: _HIGH_IMAGE_FEATURES_TASK}


def get_coding_task(task_id: str) -> CodingTask | None:
    """Return the coding task with ``task_id`` or None."""
    return _TASKS.get(task_id)


def list_coding_tasks(course_id: str | None = None) -> list[CodingTask]:
    """Return all coding tasks, optionally filtered by course."""
    tasks = list(_TASKS.values())
    if course_id:
        tasks = [t for t in tasks if t.course_id == course_id]
    return tasks


def get_visible_tests(task: CodingTask) -> list[TestCase]:
    """Return only visible tests — hidden tests never leave the backend."""
    return [t for t in task.visible_tests if not t.is_hidden]


__all__ = [
    "get_coding_task",
    "get_visible_tests",
    "list_coding_tasks",
]
