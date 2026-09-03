# Third-party digital classics / 第三方数字典籍

Taiyi Shuji's source code, original documentation, and repository example images
are released under the MIT License. The 18 processed classical-text files under
`kb/texts/` are bundled runtime materials with separate source and license
identities. The MIT License does not relicense those texts.

太乙枢机的软件代码、原创文档与仓库示例图采用 MIT License。`kb/texts/` 中随
仓库提供的 18 部处理后典籍正文具有独立的来源与许可身份，不因软件采用 MIT 而
被重新授权。

## What is included / 收录内容

The repository includes the Skill's processed knowledge base, not the raw download
staging area:

- `kb/manifest.json` binds each runtime work to its identity, processed path,
  source identity, and SHA-256;
- `kb/texts/*.md` contains work-separated, UTF-8 Markdown with structural headings,
  stable anchors, conversion metadata, and edition or verification caveats;
- `kb/assets/辅行诀/` contains repository-built structured transcriptions of the
  Tangye diagram and Jingfa rules, with direct-source anchors and regression cases.

Raw HTML snapshots, scans, and historical merged source files under the private
`refs/` staging area are not redistributed and are not runtime corpus copies.

仓库收录的是 Skill 实际运行所用的处理后知识库：清单、分书并结构化的 Markdown
正文，以及《辅行诀》汤液图与经法规则资产。原始 HTML、扫描件和历史合并源文件
不随仓库分发，也不是另一套运行正文。

## Source groups / 来源分组

The underlying historical works are generally public-domain by age. A digital
edition, transcription, selection, punctuation, or site contribution may still
carry separate terms. Each processed Markdown file retains the source site or
source-file identity, acquisition date where available, conversion method,
edition status, and source or output digest.

- **Chinese Wikisource / 中文维基文库:** `周易`, `周易参同契`, `黄帝内经素问`,
  `黄帝内经灵枢`, `黄帝内经太素`, `类经`, `诸病源候论`, and `辅行诀脏腑用药法要`.
  Wikisource contributions are available under CC BY-SA 4.0 and GFDL as described
  by its official copyright page.
- **Chinese Text Project / 中国哲学书电子化计划:** `黄庭内景五脏六腑补泻图` and
  `针灸甲乙经`. Their processed files retain the provider and snapshot identity.
  Use and redistribution remain subject to the provider's current terms.
- **中医笈成:** `外台秘要`. Its file metadata records the source commit, source
  digest, edition description, and the provider's CC0 statement for its selection,
  arrangement, punctuation, and annotations of public-domain texts.
- **Processed historical text imports / 历史电子文本处理件:** `外经微言`, `八十一难经`,
  `桂林古本伤寒杂病论`, `神农本草经`, `本草经集注`, `备急千金要方`, and `千金翼方`.
  The exact imported source-file hashes, extraction ranges, encoding, conversion
  version, and unresolved edition caveats remain in each Markdown header. The
  repository grants no additional rights over any third-party transcription or
  editorial layer that may remain in those files.

The maintainer has authorized inclusion of these processed files from publicly
downloadable source materials. Downstream users and redistributors remain
responsible for observing the terms and attribution requirements applicable to
each source. Do not infer a single corpus-wide license from this repository.

维护者已明确授权把这些来自网络公开下载来源的处理后文件纳入公开仓库。后续使用
或再分发仍应遵守各来源适用的条款与署名要求，不应把整个典籍知识库理解为单一
MIT 许可数据集。

## Official source terms / 来源条款

- [Chinese Wikisource copyright information / 中文维基文库版权信息](https://zh.wikisource.org/zh/Wikisource:%E7%89%88%E6%9D%83%E4%BF%A1%E6%81%AF)
- [Chinese Text Project FAQ and terms / 中国哲学书电子化计划 FAQ](https://ctext.org/faq)
