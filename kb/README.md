# 本地典籍区

太乙枢机的模型推理不依赖一套内置处方数据库。典籍服务只在需要核对直接原文、
出处、调用权或反面证据时，向模型提供少量连续短文。

公开仓库不分发完整数字典籍。不同来源的数字文本适用不同许可，其中部分站点
不允许整库再发布。使用者应从有权使用的来源准备自己的本地文本。

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
身份。活动检索只读取 manifest 中列出的文件；典籍正文、整章或未经选择的长行
不会直接进入模型上下文。

维护者的本地完整语料可以运行：

```bash
python3 -B tools/retrieval.py validate
python3 -B tools/test_retrieval.py
python3 -B tools/tangye.py validate
```

没有安装本地典籍时，通用契约、病例状态、角色传递和展示测试仍可运行；直接
经典引文和来源回读功能不可用。

来源与许可边界见 [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)。
