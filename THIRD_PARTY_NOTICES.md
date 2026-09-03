# Third-party materials and local corpus

Taiyi Shuji is released as software under the MIT License. That license covers
the source code, original documentation, and example images committed to this
repository. It does not relicense third-party texts or data.

The private development workspace uses a local corpus of historical Chinese
medical and philosophical works. The public repository does not distribute that
complete corpus because digital-source terms differ:

- Chinese Wikisource contributions are distributed under CC BY-SA 4.0 and GFDL;
- the Chinese Text Project permits limited quotation and private or non-profit
  academic uses, while general republication may require permission;
- other locally imported sources may have their own terms.

Users must obtain and prepare texts they are entitled to use. Each local
`kb/manifest.json` entry should preserve the source identity and a SHA-256 of the
exact Markdown file. Do not treat this repository’s MIT License as permission to
redistribute a separately acquired corpus.

Official source terms:

- Chinese Wikisource copyright information: https://zh.wikisource.org/zh/Wikisource:%E7%89%88%E6%9D%83%E4%BF%A1%E6%81%AF
- Chinese Text Project FAQ and terms: https://ctext.org/faq

The repository includes short classical quotations in schemas or test fixtures
only where needed to test source identity and anchor behavior.
