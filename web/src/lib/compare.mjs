// Public statements and the platform comparison shown in the Compare section.
//
// Rules (patchground-web SPEC): quotes are verbatim, attributed with the role the person held at the
// time, dated, and linked to a public source; an ellipsis marks every cut. Platform facts come only
// from each vendor's public pages, checked on CHECKED_ON. None of this implies an endorsement.

export const CHECKED_ON = "2 November 2026";

export const QUOTES = [
  {
    text: "Google: 90% of our engineers use the software you wrote (Homebrew), but you can’t invert a binary tree on a whiteboard…",
    who: "Max Howell",
    role: "Creator of Homebrew, after a Google interview",
    date: "June 2015",
    source: "https://web.archive.org/web/20160308100838/https://twitter.com/mxcl/status/608682016205344768",
    via: "X (archived)",
  },
  {
    text: "Hello, my name is David. I would fail to write bubble sort on a whiteboard. I look code up on the internet all the time. I don't do riddles.",
    who: "David Heinemeier Hansson",
    role: "Creator of Ruby on Rails, CTO of Basecamp",
    date: "February 2017",
    source: "https://theoutline.com/post/1166/programmers-are-confessing-their-coding-sins-to-protest-a-broken-job-interview-process",
    via: "The Outline",
  },
  {
    text: "Engineers spend most of their time understanding existing codebases, reviewing pull requests and iterating on solutions, rather than implementing algorithms from scratch.",
    who: "Canva Engineering",
    role: "On replacing its algorithms interview with AI-assisted coding",
    date: "June 2025",
    source: "https://www.canva.dev/blog/engineering/yes-you-can-use-ai-in-our-interviews/",
    via: "Canva Engineering Blog",
  },
  {
    text: "This is more representative of the developer environment that our future employees will work in, and also makes LLM-based cheating less effective.",
    who: "Meta",
    role: "Internal post on AI-enabled coding interviews",
    date: "July 2025",
    source: "https://www.404media.co/meta-is-going-to-let-job-candidates-use-ai-during-coding-tests/",
    via: "404 Media",
  },
  {
    text: "The developer’s role has changed to be an orchestrator of agents, but LeetCode-style puzzles aren’t going to help you find them.",
    who: "HackerRank",
    role: "Its own homepage, to the companies it sells interviews to",
    date: `checked ${CHECKED_ON}`,
    source: "https://www.hackerrank.com/",
    via: "hackerrank.com",
  },
  {
    text: "We found that brainteasers are a complete waste of time. … They don’t predict anything. They serve primarily to make the interviewer feel smart.",
    who: "Laszlo Bock",
    role: "SVP of People Operations at Google, on brainteaser questions",
    date: "June 2013",
    source: "https://www.nytimes.com/2013/06/20/business/in-head-hunting-big-data-may-not-be-such-a-big-deal.html",
    via: "The New York Times",
  },
];

export const ROWS = ["What you work on", "Where you write code", "Where checks run", "What you get back", "Account needed", "Source code public"];

export const PLATFORMS = [
  {
    name: "Patchground",
    ours: true,
    cells: ["A real repository with a bug report or feature ticket", "Your editor, on your machine, with any AI or none", "Docker, on your machine", "Verified outcomes: checks, regression proof, diff scope, time. No score.", "No", "Yes, Apache-2.0"],
    sources: [],
  },
  {
    name: "LeetCode",
    cells: ["4,100+ algorithm problems", "Browser editor, with a built-in AI agent on Premium credits", "LeetCode’s judge", "Accepted or not, with runtime and memory percentiles", "Yes", "No"],
    sources: [{ label: "problem list", url: "https://leetcode.com/problemset/" }, { label: "Premium", url: "https://leetcode.com/subscribe/" }],
  },
  {
    name: "HackerRank",
    cells: ["Interview Preparation Kit: arrays, hashmaps, greedy, dynamic programming, trees…", "Browser editor", "HackerRank’s servers", "Pass or fail per test case", "Yes", "No"],
    sources: [{ label: "Interview Preparation Kit", url: "https://www.hackerrank.com/interview/interview-preparation-kit" }],
  },
  {
    name: "CodeSignal",
    cells: ["Courses with an AI tutor, and certified coding assessments", "Browser IDE", "CodeSignal’s servers", "An assessment score from 200 to 600", "Yes", "No"],
    sources: [{ label: "Learn", url: "https://codesignal.com/learn" }, { label: "assessment score", url: "https://support.codesignal.com/hc/en-us/articles/13261190299287-Understanding-Assessment-Score" }],
  },
  {
    name: "Exercism",
    cells: ["8,700+ small exercises across 85 languages", "Browser, or your editor through its CLI", "Your machine, or Exercism’s test runner", "Passing tests, automated analysis, optional human mentoring", "Yes; the CLI uses your API token", "Yes, on GitHub"],
    sources: [{ label: "homepage", url: "https://exercism.org/" }, { label: "working locally", url: "https://exercism.org/docs/using/solving-exercises/working-locally" }],
  },
  {
    name: "CodeCrafters",
    cells: ["Build your own Redis, Git, SQLite…", "Your editor; you submit with git push or its CLI", "CodeCrafters’ test runners", "Stage-by-stage test results", "Yes", "Its test runners are, on GitHub"],
    sources: [{ label: "how challenges work", url: "https://docs.codecrafters.io/challenges/how-challenges-work" }, { label: "CLI", url: "https://docs.codecrafters.io/cli/usage" }, { label: "redis-tester", url: "https://github.com/codecrafters-io/redis-tester" }],
  },
];
