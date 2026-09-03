# 处理后数字典籍知识库

本目录是太乙枢机的必需运行依赖，不是留给使用者自行补齐的空接口。仓库公开的
是 Skill 实际读取的处理后知识库，不是下载时的原始页面、扫描件或历史合并源文件。

太乙枢机的模型推理不依赖内置处方查询库。典籍服务只在需要核对直接原文、出处、
调用权、反面证据或决定性边界时，从本目录选择少量连续短文。

## 目录约定

```text
kb/
├── manifest.json
├── texts/
│   └── <一部典籍一份 Markdown>
└── assets/
    └── <确有必要的配套材料>
```

`manifest.json` 为每部作品记录稳定 `work_id`、标题、相对路径、SHA-256 和来源
身份。当前清单登记 18 部处理后 Markdown 正文和 5 个结构化资产。正文已经完成
分书、编码统一、结构标题和稳定锚点处理；文件头继续保留来源、底本状态、转换
方式、原文件哈希或来源快照身份。`assets/辅行诀/` 保存从原文整理并由直接来源
锚点回验的汤液图、经法规则、五味关系、二十五味矩阵与经方测试材料。

活动检索只读取 manifest 中列出的唯一正文。调用卡在 `spec/retrieval_cards.json`，
进程内定位索引由这些 Markdown 临时重建；二者都不保存第二份原文，也不是证据。
典籍正文、整章或未经选择的长行不会直接进入模型上下文。

完整性检查：

```bash
python3 -B tools/retrieval.py validate
python3 -B tools/test_retrieval.py
python3 -B tools/tangye.py validate
```

`manifest.json`、其登记正文或结构化资产缺失、被替换或 SHA-256 不符时，Skill
安装不完整，正式运行必须停止，不得静默降级为无来源运行。

来源与许可边界见 [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)。
