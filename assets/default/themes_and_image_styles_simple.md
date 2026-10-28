### 主题（theme）和图片风格（image_styles）选择依据（详细）

#### 主题（theme）选择逻辑

根据文章的整体气质和内容类型，从以下 15 个主题中匹配：

| 内容气质 | 推荐主题 |
| :--- | :--- |
| AI / 产品 / 深度分析 | `refined-blue`、`business-navy`、`sage-premium` |
| 技术 / SDK / 工程 | `minimal-mono`、`minimal-bw`、`academic-paper` |
| 新闻 / 热点 / 速读 | `news-bold`、`warm-editorial` |
| 人文 / 随笔 / 文化 | `ink-wash`、`elegant-ink`、`magazine-grid` |
| 生活 / 美食 / 旅行 | `warm-orange`、`mint-fresh`、`sunset-coral` |
| 时尚 / 美妆 / 情感 | `girly-pink`、`sunset-coral` |

#### 图片风格（image_styles）选择逻辑

根据文章内容的主要类型，从以下映射表中选择 1-3 个图片风格：

| 内容类型 | 首选风格 | 备选风格 |
| :--- | :--- | :--- |
| AI/产品深挖/功能拆解 | `infographic-warm` | `infographic-blue`、`hand-drawn-blue` |
| 技术/架构/SDK/协议 | `infographic-blue` | `blue`、`hand-drawn-blue` |
| 步骤教程/工具对比 | `flat-editorial` | `warm-handdrawn`、`knowledge-card` |
| 数据/报告/趋势 | `data-chart` | `infographic-blue` |
| 热点/标题党/punchy 短句 | `marker-lime` | 其他 `marker-*` |
| 生活方式/清单/盘点 | `warm-handdrawn` | `xiaohongshu-colorful`、`mint` |
| 观点/人文/深度评论 | `morandi` | `magazine-editorial` |
| 段子/吐槽/互联网幽默 | `slice-of-life` | `meme-illustration`（慎用） |
| 体验分享/有人物叙事 | `illustrated-warm` | `slice-of-life` |

**选择原则**：
1. 优先选择与内容类型最匹配的 `首选风格`。
2. 如果文章包含多种类型元素（如“技术教程 + 数据对比”），可选取 2-3 个备选风格混合使用。
3. 避免选择与文章基调冲突的风格（如严肃技术文章不要选 `xiaohongshu-colorful`）。