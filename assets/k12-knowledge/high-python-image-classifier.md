# 从零实现 Python 图像分类器
## 适用学段
高中十至十二年级。学生应掌握 Python 变量、列表、函数、循环与条件判断，能够阅读均值和比例，理解训练数据与测试数据必须分离。本课用小型灰度数组说明完整流程，不把课堂示例包装成可直接用于真实人脸、医疗或安防场景的产品。

## 学习目标
完成本课后，学生能够把灰度图像表示为二维数值数组并解释行、列与像素强度；能够编写函数从数组提取平均亮度、上下区域差异和简单边缘变化等特征；能够说明最近质心分类器如何用每类训练样本的平均特征形成质心，并以距离选择类别；能够使用固定随机种子完成分层训练测试划分；能够计算准确率、逐类召回情况和混淆矩阵；能够检查数据泄漏、类别不均衡与分布变化；能够分析手工特征、距离度量、样本规模和运行成本带来的限制；能够说明课堂模型为何不适合自动处理高风险决定，并提出人工复核和持续监测方案。

## 核心知识
灰度图像可以表示为二维数组。数组的每一行对应图像的一行像素，每个数表示亮度，常见范围从黑到白逐渐增大。彩色图像通常还包含多个颜色通道。本课把图片缩小为相同尺寸的灰度数组，目的是突出数据流，而不是获得真实应用的高精度。若输入尺寸不同，可以先裁剪、填充或缩放，但每种处理都会改变信息，应记录方法并在训练与预测时保持一致。

直接比较所有像素是一种方法，但在小型教学实验中，我们先手工提取特征。平均亮度描述整体明暗；上半部分与下半部分的亮度差可以反映亮区域位置；相邻像素差的平均值可以粗略描述边缘或纹理变化。这些特征把大量像素压缩为少量数字，计算快、容易解释，却会丢失形状细节。两张结构完全不同的图片可能具有相同平均亮度，因此特征必须围绕任务设计，并通过错误案例检验。

最近质心分类器为每个类别计算一个代表点。训练阶段先提取所有训练图像的特征，再按标签分组，对每个特征维度求平均，得到该类质心。预测新图像时，提取同样的特征，计算它到每个质心的距离，选择距离最近的类别。常用的欧氏距离会把各维度差异平方后相加。若某个特征的数值范围远大于其他特征，它会主导距离，因此实际项目常需要标准化。本示例特征都压缩到相近范围，仍应在报告中说明这一假设。

最近质心方法的时间开销较容易估计。训练时需要遍历训练样本并累计每类特征；预测一个样本时，需要与每个类别质心比较。类别和特征数量增加，计算量近似随两者乘积增长。它不保存所有训练样本，内存需求较小，但一个平均质心只能表达每类一个中心。当同一类别存在多个相距很远的子群，或类别边界弯曲复杂时，单个质心可能表现很差。

特征标准化需要只从训练集计算参数。例如训练特征的均值和尺度应由训练样本得到，再原样应用到测试与新输入；若把测试集一起用于计算，评价就已经看到测试分布。标准化也不是机械步骤：亮度差、纹理差和类别距离是否适合使用同一种尺度，应结合数据含义、异常值和距离度量实验验证。所有变换都应保存参数与版本，确保线上预测和离线训练执行同一流程。

训练测试划分必须发生在任何从数据学习的步骤之前。如果先用全部数据计算标准化均值、选择“最有效”特征或删除难例，再划分测试集，就把测试信息泄漏给训练流程。分层划分尽量保持每类比例，固定随机种子让结果可复现。若图片来自视频连续帧、同一个人的多次拍摄或同一原图的增强版本，应按来源分组划分，否则极相似图片会跨越训练与测试集合。

准确率是正确预测数占全部测试数的比例。混淆矩阵以真实类别为行、预测类别为列，展示每一种错误方向。逐类召回率关注某真实类别中有多少被找回。若类别不平衡，宏平均会先分别计算各类指标再平均，使少数类拥有相同权重。评价报告还应给出测试样本数和不确定性。小测试集上多答对一张图片就可能大幅改变百分比，不能据此宣称普遍有效。

数据分布会变化。课堂训练使用居中的黑白图形，真实输入可能倾斜、模糊、有阴影、来自不同设备或包含训练中未定义的类别。分类器通常仍会强行选择某个已知类别，因此应用层需要输入质量检查、拒绝机制和“未知”处理。部署后还要监测错误，保留版本和回滚能力。模型分数不是事实证明，更不是对人的价值判断。

### 可运行的 Python 示例

下面代码只使用 Python 标准库。每个“图像”是四行四列的灰度数组，标签 `top` 表示上部更亮，`bottom` 表示下部更亮。代码包含特征提取、分层划分、质心训练、预测、准确率和混淆矩阵。示例代码少于八十行。

```python
from collections import defaultdict
import math
import random


def features(image):
    rows, cols = len(image), len(image[0])
    pixels = [value / 255 for row in image for value in row]
    half = rows // 2
    top = sum(image[r][c] for r in range(half) for c in range(cols))
    bottom = sum(image[r][c] for r in range(half, rows) for c in range(cols))
    region_size = half * cols * 255
    edges = []
    for row in image:
        edges.extend(abs(row[c] - row[c - 1]) / 255 for c in range(1, cols))
    return [sum(pixels) / len(pixels), (top - bottom) / region_size, sum(edges) / len(edges)]


def stratified_split(samples, test_per_class=1, seed=7):
    groups = defaultdict(list)
    for image, label in samples:
        groups[label].append((image, label))
    rng = random.Random(seed)
    train, test = [], []
    for group in groups.values():
        rng.shuffle(group)
        test.extend(group[:test_per_class])
        train.extend(group[test_per_class:])
    return train, test


def fit(samples):
    grouped = defaultdict(list)
    for image, label in samples:
        grouped[label].append(features(image))
    return {
        label: [sum(column) / len(vectors) for column in zip(*vectors)]
        for label, vectors in grouped.items()
    }


def predict(image, centroids):
    vector = features(image)
    distance = lambda center: math.sqrt(sum((a - b) ** 2 for a, b in zip(vector, center)))
    return min(centroids, key=lambda label: distance(centroids[label]))


TOP = [[240] * 4, [210] * 4, [40] * 4, [20] * 4]
BOTTOM = list(reversed(TOP))
samples = [
    ([[max(0, min(255, value + delta)) for value in row] for row in base], label)
    for base, label in [(TOP, "top"), (BOTTOM, "bottom")]
    for delta in (-20, -10, 0, 10, 20, 30)
]
train, test = stratified_split(samples, test_per_class=2)
centroids = fit(train)
matrix = {actual: {predicted: 0 for predicted in centroids} for actual in centroids}
for image, actual in test:
    matrix[actual][predict(image, centroids)] += 1
correct = sum(matrix[label][label] for label in matrix)
print("accuracy:", correct / len(test))
print("confusion matrix:", matrix)
```

运行后应先检查训练集与测试集数量，再观察混淆矩阵。可以把某一测试图上下翻转、增加横向条纹或整体变暗，记录特征与预测如何改变。不要为了让结果好看而删除错误案例；错误正是理解特征局限的材料。

## 示例
设想要区分“上方亮块”和“下方亮块”。平均亮度无法区分它们，因为总亮度可能相同；上下区域差异却能表达亮块位置。若再加入“条纹”和“纯色”类别，相邻像素差可能有帮助。这个过程展示了特征工程与任务定义的关系：先明确要区分什么，再寻找保留该差异的表示。

将同一代码用于真实照片会遇到尺寸、旋转、背景和颜色差异。若训练集只含白底居中图形，模型可能把背景当成主要线索。在测试中加入不同背景后，混淆矩阵会暴露问题。改进可以包括更有代表性的数据、归一化、位置不敏感的特征，或选择能学习局部结构的模型。但复杂模型仍需要独立测试、偏差检查和责任机制，并不会自动解决数据问题。

## 练习
一、手工计算两张四乘四数组的平均亮度和上下区域差异，预测哪一个特征能区分“上亮下暗”与“上暗下亮”。再构造一对让平均亮度相同但结构不同的数组。

二、运行示例，分别修改随机种子和每类测试数量。记录训练样本数、测试样本数、准确率和混淆矩阵。解释为什么测试样本很少时一次错误会产生很大比例变化。

三、增加 `striped` 类别并设计至少六张数组。先不修改特征，观察错误；再加入纵向相邻像素差，比较变化。只使用训练集决定新特征，保留一批新测试数组做最终评价。

四、制造数据泄漏：先复制一个样本，再让副本分别进入训练和测试。比较结果后恢复按原始来源分组的划分，说明为什么“看似更高的分数”不代表泛化能力提升。

五、为分类器写一份模型卡摘要，包括预期用途、禁止用途、训练数据范围、特征、指标、已知失败情境、隐私处理、人工复核与停止使用条件。

六、分析复杂度：若特征从三个增加到三十个、类别从两个增加到二十个，预测阶段需要比较的数值差异如何变化？讨论标准化、内存、响应时间和解释成本之间的工程权衡。

## 常见误解
误解一：“数组完整保存了图片意义。”数组记录像素数值，语义来自任务、标签和模型解释；相同数组在不同任务中含义可能不同。

误解二：“手工特征可解释，所以一定公平。”可解释性便于检查，但特征仍可能遗漏重要变化或成为敏感属性的替代变量，必须用代表性数据分组评价。

误解三：“固定随机种子证明模型普遍稳定。”种子只帮助复现一次划分。应使用多次合理划分、交叉验证或独立外部数据评估波动，同时保留最终测试集。

误解四：“准确率达到高值就能部署。”还需检查类别错误、未知输入、分布变化、资源成本、隐私、安全、人工复核和错误后果。高风险用途需要更严格的专业验证。

误解五：“更复杂的神经网络会自动消除偏差。”复杂模型可能学习更强表示，也可能放大数据中的不平衡与历史偏差。数据治理和评价设计不可省略。

误解六：“删除姓名就实现匿名。”图像本身、文件元数据、精确时间地点和其他组合特征仍可能识别人，匿名化需要系统评估重识别风险。

## 安全与伦理
本实验只使用人工构造数组或明确授权、低风险的公共物体图片，不收集同学人脸、健康、身份、精确位置或家庭信息。数据按最小必要原则保存，记录来源、授权、访问者、期限和删除方式。不得把课堂分类器用于门禁、考试评分、心理判断、医疗建议或其他影响个人权益的决定。报告必须同时展示成功案例、错误案例、各类样本数和已知限制。若不同群体或设备条件下性能差异明显，应暂停使用并调查采样、标签、特征和流程。为使用者提供人工复核、纠错、申诉、退出和数据删除渠道。依赖第三方库时应核对许可证、版本和安全更新；输出模型与数据文件不得包含秘密密钥或个人信息。

## 参考来源
- UNESCO：《AI Competency Framework for Students》，覆盖以人为本、AI 技术理解、伦理和系统设计能力。https://www.unesco.org/en/articles/ai-competency-framework-students
- NIST：《AI Risk Management Framework》，提供有效可靠、安全、透明、隐私增强和公平风险的官方管理框架。https://www.nist.gov/itl/ai-risk-management-framework
- Python 官方教程：《Data Structures》，说明列表、推导式、字典与标准数据结构。https://docs.python.org/3/tutorial/datastructures.html
- NumPy 官方用户指南：《NumPy quickstart》，说明多维数组、轴、形状和数组运算；真实图像数组项目可据此扩展。https://numpy.org/doc/stable/user/quickstart.html
- scikit-learn 官方文档：《NearestCentroid》，说明最近质心分类器的接口、距离与特征缩放注意事项。https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.NearestCentroid.html
- scikit-learn 官方文档：《train_test_split》《accuracy_score》《confusion_matrix》，提供划分与分类评价的标准实现。https://scikit-learn.org/stable/modules/classes.html#module-sklearn.model_selection
- Google for Developers：《Machine Learning Crash Course》，涵盖特征、分类、过拟合、数据集与公平性。https://developers.google.com/machine-learning/crash-course
