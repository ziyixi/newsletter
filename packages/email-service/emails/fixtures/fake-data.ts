import type { NewsletterProps } from "../types";

// ─────────────────────────────────────────────
// Fake / preview data for the newsletter template
// Used as default props so `email dev` works out of the box.
// Bilingual Chinese / English content. Temperatures in °C.
// ─────────────────────────────────────────────

export const fakeData: NewsletterProps = {
  recipientName: "Ziyi",
  date: "2026年2月8日 · 星期日",

  // ── Weather (°C) ──────────────────────────
  weather: {
    location: "圣尼维尔，加州",
    condition: "多云转晴",
    icon: "⛅",
    tempCurrent: 14,
    tempHigh: 17,
    tempLow: 9,
    summary:
      "午后多云间晴，傍晚有小概率阵雨。西风约19公里/时。适合出门散步，建议携带薄外套。",
    forecasts: [
      { label: "周一", icon: "☀️", condition: "晴", high: 19, low: 10 },
      { label: "周二", icon: "🌤", condition: "大部晴朗", high: 18, low: 11 },
      { label: "周三", icon: "🌧", condition: "小雨", high: 14, low: 8 },
    ],
    sunrise: "06:58",
    sunset: "17:42",
    dayLength: "10时44分",
    goldenHour: "17:12",
    astroNote: "今晚木星将在西南方天空清晰可见，是观星的好时机。",
  },

  // ── Top News ──────────────────────────────
  topNews: [
    {
      headline: "突破性聚变反应堆连续72小时实现净能量增益",
      summary:
        "美国国家点火装置的科学家宣布一项历史性里程碑——聚变反应持续输出净能量长达三天，标志着商业聚变能源迈出关键一步。",
      source: "Reuters",
      url: "https://example.com/fusion-breakthrough",
      category: "科学",
    },
    {
      headline: "美联储暗示因就业数据强劲暂停降息",
      summary:
        "美联储维持利率在3.75%不变，理由是就业市场表现强劲以及服务业通胀持续高于目标。",
      source: "Wall Street Journal",
      url: "https://example.com/fed-rates",
      category: "经济",
    },
    {
      headline: "SpaceX星舰完成首次载人登月任务",
      summary:
        "四名宇航员在月球南极附近着陆，这一里程碑任务为2030年前建立永久月球基地铺平了道路。",
      source: "NASA / AP",
      url: "https://example.com/starship-moon",
      category: "航天",
    },
    {
      headline: "欧盟通过全面AI问责法案，开创全球先例",
      summary:
        "该立法要求对部署在欧盟的高风险AI系统进行透明度报告、偏见审计和责任框架建设。",
      source: "BBC News",
      url: "https://example.com/eu-ai-act",
      category: "科技",
    },
    {
      headline: "金州勇士队加时赛逆转锁定季后赛席位",
      summary:
        "库里砍下41分，勇士128-125加时击败凯尔特人，锁定西部第六号种子。",
      source: "ESPN",
      url: "https://example.com/warriors-playoffs",
      category: "体育",
    },
  ],

  // ── Hacker News ───────────────────────────
  hnStories: [
    {
      title: "Show HN: I built a real-time collaborative code editor in Rust",
      titleCn: "我用 Rust 构建了一个实时协作代码编辑器",
      url: "https://example.com/hn-1",
      points: 842,
      commentCount: 234,
      hnUrl: "https://news.ycombinator.com/item?id=1",
    },
    {
      title: "SQLite is not a toy database (2024)",
      titleCn: "SQLite 不是玩具数据库（2024）",
      url: "https://example.com/hn-2",
      points: 631,
      commentCount: 187,
      hnUrl: "https://news.ycombinator.com/item?id=2",
    },
    {
      title: "Why we moved from Kubernetes back to bare metal",
      titleCn: "为什么我们从 Kubernetes 迁回了裸金属服务器",
      url: "https://example.com/hn-3",
      points: 523,
      commentCount: 312,
      hnUrl: "https://news.ycombinator.com/item?id=3",
    },
    {
      title: "A visual guide to quantization in LLMs",
      titleCn: "大语言模型量化技术图解指南",
      url: "https://example.com/hn-4",
      points: 489,
      commentCount: 98,
      hnUrl: "https://news.ycombinator.com/item?id=4",
    },
    {
      title: "The unreasonable effectiveness of plain text",
      titleCn: "纯文本的不合理有效性",
      url: "https://example.com/hn-5",
      points: 412,
      commentCount: 156,
      hnUrl: "https://news.ycombinator.com/item?id=5",
    },
  ],

  // ── Stocks (ETFs + key tickers) ────────────
  stocks: [
    {
      symbol: "QQQ",
      companyName: "纳斯达克100 ETF",
      price: 527.83,
      change: 4.21,
      changePercent: 0.8,
    },
    {
      symbol: "VOO",
      companyName: "标普500 ETF",
      price: 543.19,
      change: 2.67,
      changePercent: 0.49,
    },
    {
      symbol: "GLD",
      companyName: "黄金 ETF",
      price: 234.56,
      change: -0.89,
      changePercent: -0.38,
    },
    {
      symbol: "SLV",
      companyName: "白银 ETF",
      price: 28.14,
      change: 0.32,
      changePercent: 1.15,
    },
    {
      symbol: "TSLA",
      companyName: "特斯拉",
      price: 312.09,
      change: -8.74,
      changePercent: -2.73,
    },
    {
      symbol: "NVDA",
      companyName: "英伟达",
      price: 845.21,
      change: 12.35,
      changePercent: 1.48,
    },
  ],

  // ── GitHub Trending ───────────────────────
  githubTrending: [
    {
      name: "astral-sh/ruff",
      description: "An extremely fast Python linter and code formatter, written in Rust.",
      descriptionCn: "一个用 Rust 编写的极速 Python 代码检查与格式化工具。",
      language: "Python",
      stars: 42300,
      todayStars: 186,
      url: "https://github.com/astral-sh/ruff",
    },
    {
      name: "microsoft/TypeScript",
      description: "TypeScript is a superset of JavaScript that compiles to clean JavaScript output.",
      descriptionCn: "TypeScript 是 JavaScript 的超集，编译生成简洁的 JavaScript 代码。",
      language: "overall",
      stars: 102000,
      todayStars: 220,
      url: "https://github.com/microsoft/TypeScript",
    },
    {
      name: "ollama/ollama",
      description: "Get up and running with Llama 3, Mistral, Gemma, and other large language models.",
      descriptionCn: "快速启动并运行 Llama 3、Mistral、Gemma 等大语言模型。",
      language: "Go",
      stars: 108000,
      todayStars: 312,
      url: "https://github.com/ollama/ollama",
    },
    {
      name: "vllm-project/vllm",
      description: "A high-throughput and memory-efficient inference and serving engine for LLMs",
      descriptionCn: "高吞吐、低内存占用的大语言模型推理与服务引擎",
      language: "Python",
      stars: 45800,
      todayStars: 154,
      url: "https://github.com/vllm-project/vllm",
    },
  ],

  // ── arXiv Papers ──────────────────────────
  arxivPapers: [
    {
      title: "Scaling Sparse Mixture-of-Experts to Trillion Parameters",
      titleCn: "将稀疏混合专家模型扩展到万亿参数规模",
      summary: "提出了一种新的路由策略，使 MoE 模型在万亿参数级别下仍能保持高效训练和推理。",
      authors: "Zhang et al.",
      url: "https://arxiv.org/abs/2602.00001",
      category: "LLM",
    },
    {
      title: "InfiniContext: Efficient Infinite-Length Context for LLMs via Hierarchical Compression",
      titleCn: "InfiniContext：通过分层压缩实现 LLM 的高效无限上下文",
      summary: "提出分层压缩方案，在不增加显存的情况下将上下文窗口扩展到百万级 token。",
      authors: "Li, Wang, Chen",
      url: "https://arxiv.org/abs/2602.00002",
      category: "LLM",
    },
    {
      title: "GPU-Aware MPI Collectives for Exascale Simulations",
      titleCn: "面向百亿亿次模拟的 GPU 感知 MPI 集合通信",
      summary: "优化了 GPU 集群上的 MPI 集合通信原语，在百亿亿次规模模拟中实现近线性扩展。",
      authors: "Park, Johnson et al.",
      url: "https://arxiv.org/abs/2602.00003",
      category: "HPC",
    },
  ],

  // ── Exchange Rates ────────────────────────
  exchangeRates: [
    {
      pair: "USD/CNY",
      rate: 7.2461,
      change: -0.0023,
      changePercent: -0.03,
      displayName: "美元/人民币",
    },
  ],

  // ── Custom Sections ───────────────────────
  customSections: [
    {
      title: "个人备忘",
      icon: "📝",
      contentHtml: `
        <p style="margin: 0 0 8px 0;">
          <strong>提醒：</strong>周三下午2点 — 牙医预约
        </p>
        <p style="margin: 0 0 8px 0;">
          继续阅读《数据密集型应用系统设计》第9章 — 一致性与共识
        </p>
        <p style="margin: 0;">
          🎂 妈妈的生日在下周六 — 记得订花！
        </p>
      `,
    },
  ],
};
