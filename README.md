# 太乙枢机

[English](README.en.md) · [MIT License](LICENSE)

太乙枢机是一个主要为 Codex 设计并完成运行验收的中医研析 Skill。它把经典解释、
方剂分析、病例辨证、同案复察和简要个人病历放在同一条可核验主线上，并保留必要
的来源、结果身份和失败边界。

项目默认使用 Codex 等宿主已有的模型、原生子代理、登录状态和额度，不要求单独
配置模型 API。模型预训练知识和中医推理是主线；本地典籍服务只在需要核对直接
原文、出处、调用权或反面证据时提供少量连续短文。

**兼容状态：** 当前只在 Codex 上完成开发和运行验收，尚未在其他 Agent 宿主上
进行兼容测试。纯图片报告尤其依赖具备图像生成、局部编辑和原图复核能力的 Codex
环境；不具备这些能力时，核心文字分析仍可运行，但不能声称支持同等的纯图生产链。

> 本项目用于中医经典研究、方剂研析和个人学习，不是医疗器械，也不提供可直接
> 执行的诊断或处方。病例与方药结论必须由具备相应资质的专业人员结合现实情况
> 复核。示例图片只展示报告表达方式，不证明医学结论有效。

## 效果示意

以下示例覆盖从气化方向到证机辨析、病例病机和方药结构的关键分析链，不只展示
方剂清单。前两页来自同一份无方名方剂的条件性分析，第三页展示脱敏病例的病因
病机与辨证关系。纯图报告是正式文字结果的可选表达，不改变分析内容，也不形成
第二套医学状态。

<table>
  <tr>
    <td width="50%" align="center">
      <img src="docs/images/qi-transformation-r0.png" alt="太乙枢机 R0 气化分析"><br>
      <strong>R0 · 气化分析</strong><br>一气周流、开合转枢与五行方向
    </td>
    <td width="50%" align="center">
      <img src="docs/images/conditional-pattern-r1.png" alt="太乙枢机 R1 条件性证机分析"><br>
      <strong>R1 · 条件性证机</strong><br>人体气化、病势关系与辨证边界
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <img src="docs/images/case-pattern-mechanism.png" alt="太乙枢机病例病因病机与辨证"><br>
      <strong>病例 · 病因病机与辨证</strong><br>由本轮事实形成证机链，保留待核边界
    </td>
    <td width="50%" align="center">
      <img src="docs/images/formula-groups.png" alt="太乙枢机方药结构分析"><br>
      <strong>R2 · 方药结构</strong><br>治法方向与方内分组关系
    </td>
  </tr>
</table>

## 主要功能

| 功能 | 说明 |
|---|---|
| 经典解释 | 解释经典原文、概念与跨书关系；直接经典主张可绑定短原文和文档锚点 |
| 方剂分析 | 支持有方名、无方名、一味或多味组成、同方续析和方剂比较；没有患者事实时保持条件性 |
| 病例辨证 | 在中医体系内整理本轮事实，依次完成元典关系、医学转译、辨证和方药建议 |
| 同案复察 | 绑定明确父轮，对照上轮预测与本轮实况，重新判断守方、调整、转方或重辨 |
| 个人病历 | 保存事实、含混项、医者历史意见、实际用方、治疗反应、纠正和正式结果身份 |
| 红方审计 | 方剂、病例和复察使用一个隔离红方；只有实质冲突才执行一次 Stage C 综合 |
| 文字与可视化 | 默认输出完整文字结果；用户明确要求后，可从同一正式结果生成只读 H5 或纯图报告 |

## 推理主线

正式任务使用三个因果职责：

1. **R0**：形成一气、阴阳、《周易》关系及必要的五行方向，不提前下沉为脏腑、
   六经、证型或治法。
2. **R1**：把 R0 转译到人体气化、六经八纲、脏腑经络、病势和方证，并通过候选
   与反证回验收敛核心证机。
3. **R2**：完成治法、全方结构、条件性建议、Day 1／2／3 观察和退出边界。

R0—R2 由宿主在同一上下文中连续完成。方剂、病例和复察随后调用一个不继承宿主
对话的隔离红方；存在实质冲突时，宿主只综合一次，不建立固定多代理流水线或投票。

## 运行环境

- Codex，当前主要且唯一完成兼容验收的 Agent 宿主；
- 宿主能够创建一个隔离子代理，用于红方审计；
- Python 3.10 或更高版本；
- `jsonschema>=4.23,<5`；
- macOS 或 Linux。Windows 建议使用 WSL，当前尚未单独验收；
- 生成 H5 只需本仓库脚本；纯图报告需要支持图像生成、局部编辑和原图查看的
  Codex 环境。

项目没有独立模型 API 依赖。若宿主不能创建隔离子代理，方剂、病例和复察不能
声称完成正式红方审计。其他 Agent 即使具备 Skill、文件和终端能力，也尚未经过
本项目的安装、子代理、脚本调用、结果提交或图片生成兼容测试。

## 安装

```bash
git clone https://github.com/gethlx/taiyi.git
cd taiyi

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Codex 建议使用符号链接安装 Skill，保留它与仓库中 `spec/`、`tools/`、`kb/` 的
相对关系：

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skill/taiyi-shuji" ~/.codex/skills/taiyi-shuji
```

若目标位置已经存在同名 Skill，请先自行确认保留、改名或更新方式，不要直接
覆盖已有目录。安装或更新后新建一个宿主任务，使宿主重新加载 Skill。

## 用法

在宿主对话中明确调用 `$taiyi-shuji`。常见请求如下：

```text
使用 $taiyi-shuji 解释《周易》“一阴一阳之谓道”与《参同契》的关系。
```

```text
使用 $taiyi-shuji 分析以下无方名组成：茵陈、北败酱草、垂盆草、栀子……
没有患者事实，只做条件性方义、方证和 Day 1／2／3 观察。
```

```text
使用 $taiyi-shuji 建立本次病例事实并进行中医辨证。以下是患者原话：……
```

```text
使用 $taiyi-shuji 复察刚才激活的同一病例。上次处理后出现的新变化是：……
```

```text
为当前正式结果生成移动端只读 H5。
```

只新增、读取或纠正病历事实时，Skill 不会启动完整医学主链。已有正式结果后的
普通解释也不会新建 run、turn 或 result。假设改方使用一个写时复制沙盘，不会
改写正式病例。

## 本地典籍

公开仓库不附带完整数字典籍。不同数字来源的再分发许可并不一致，部分来源仅
允许私人或有限学术使用。直接原文检索需要使用者在 `kb/` 下安装自己有权使用的
Markdown 语料和 `manifest.json`；目录格式见 [`kb/README.md`](kb/README.md)。

没有本地典籍时，模型仍可执行一般中医推理，但不能把未回读的内容包装成直接
经典引文或已核验出处。

## 测试

公开源码检查：

```bash
python3 -B tools/validate.py
```

安装了完整本地典籍后，同一命令会额外运行检索、原文回读、汤液规则和直接来源
测试。也可以单独执行：

```bash
python3 -B tools/retrieval.py validate
python3 -B tools/test_retrieval.py
python3 -B tools/tangye.py validate
```

机器测试只判断身份、守恒、来源、角色隔离和原子提交等确定性边界，不判断阴阳、
病机、方义、药性、治法或红方医学质量。

## 目录

```text
skill/taiyi-shuji/   Skill 入口、角色参考、脚本与展示资产
spec/                角色提示、机器契约、Schema 与测试数据
tools/               契约、检索、证据服务和确定性测试
kb/                  使用者自行安装的本地典籍区
docs/images/         README 使用的纯图报告示例
```

产品边界见 [`PRODUCT.md`](PRODUCT.md)，理论职责见 [`THEORY_CORE.md`](THEORY_CORE.md)，
实施架构见 [`ARCHITECTURE.md`](ARCHITECTURE.md)，机器契约见
[`spec/MACHINE_CONTRACT.md`](spec/MACHINE_CONTRACT.md)。

## 许可

软件代码、原创文档和仓库内示例图采用 [MIT License](LICENSE)。第三方材料和本地
典籍不因本软件许可证而被重新授权，详见
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
