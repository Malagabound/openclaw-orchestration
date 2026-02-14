# OpenClaw Security Article Analysis

**Source:** Forwarded from Alan - The Code newsletter
**Date:** 2026-02-09

## Full Email Content

This is the email that talks about arranging agents in a team, have you looked through this and  made changes based on its recommendations?


Thanks,

Alan Walker
801-867-2345



Sent with Spark
---------- Forwarded message ----------
From: Alan Walker <alan@originutah.com>
Date: Feb 9, 2026 at 6:35 AM -0700
To: George Botanica <george@originutah.com>
Subject: Fwd: 🎯 OpenClaw has a security problem

> Read the article about organizing agents in a team and identify if there are any takeaways we can implement in our own environment.
>
> Thanks,
>
> Alan Walker
> 801-867-2345
>
>
>
> ---------- Forwarded message ----------
> From: The Code <thecode@mail.joinsuperhuman.ai>
> Date: Feb 9, 2026 at 6:02 AM -0700
> To: alan@originutah.com <alan@originutah.com>
> Subject: 🎯 OpenClaw has a security problem
>
> > Also: How to build a team of agents
> > February 09, 2026   |   Read Online
> > Welcome back. Did you know that OpenAI and Anthropic engineers don't use the same models available to the public? They have unlimited access to faster versions. Anthropic is now bringing one of those models directly to you.
> > Today: How 6 AI agents autonomously operate a website, new security threats to watch out for, building custom skills, and how to ship features faster.
> >
> > Today’s Insights
> >
> > • > > Powerful new upgrades and tools for devs
> > • > > How to organize your agents like a team
> > • > > Build n8n workflows from a single prompt
> > • > > Trending social posts, top repos, new research & more
> >
> >
> > Welcome to The Code. This is a 2x weekly email that cuts through the noise to help devs, engineers, and technical leaders find high-signal news, releases, and resources in 5 minutes or less. You can sign up or share this email here.
> >
> > TODAY IN PROGRAMMING
> > CEO of Anthropic, Dario Amodei
> > Anthropic unveiled a faster Claude Code for devs: The AI lab just rolled out "fast mode" for Claude Code, delivering 2.5x-faster responses from its Opus 4.6 model. It's designed for devs who need quick feedback during live debugging or rapid code iteration, and it uses the exact same intelligence as the standard version. The tradeoff: higher per-token costs. Anthropic is offering a 50% launch discount through February 16 and credits to help teams try it out.
> > OpenClaw partners with VirusTotal to crack down on malicious AI agent skills: The partnership brings automatic security scanning to ClawHub, OpenClaw's skill marketplace, where roughly 7% of listings were recently found to contain critical security flaws. Every published skill is now analyzed using VirusTotal's AI-powered Code Insight tool, which flags suspicious behavior and blocks anything deemed malicious. Active skills are also re-scanned daily, giving dev teams an added layer of protection.
> > AI.com goes live as an autonomous agent platform: After a record $70M domain purchase, Crypto. com’s founder launched ai.com in beta during the Super Bowl. The platform spins up a personal AI agent for every user, each running on a fully functional PC that can handle tasks autonomously, including writing code on the fly. It's built on OpenClaw, the viral open-source agent framework.
> >
> > PRESENTED BY GENSTORE
> > Building a business? Multiply your output with an AI founding team
> > Genstore gives solo sellers something you’ve never had—AI co-founders that handle the work that wears you down, so you can focus on your brand, product, and vision.
> > With Genstore, you can:
> >
> > • > > Turn your story into a fully-built store in minutes (no code needed)
> > • > > Delegate research, marketing, and ops to AI agents
> > • > > Grow your business without burning out doing ten jobs alone
> >
> > Ready to launch your store today?
> > Try a Genstore Growth plan for just $1 (basic plan costs nothing).
> >
> > INSIGHT
> > How to organize your agents like a team
> > Source: The Code, Superhuman
> > The org design gap is real. A Stanford research team recently published a paper that should change how engineering leaders think about multi-agent systems. They found that LLM agent teams consistently underperformed their single best member by up to 37.6%. The reason is that agents blended strong and weak inputs together instead of deferring to whoever had the best answer.
> > The teams getting results share one pattern. Three engineers at infrastructure company StrongDM built a "Software Factory" where AI agents write, test, and ship production security software with zero human code review. The playbook is humans set intent, structured specs replace prompts, agents own specific domains, and automated verification replaces review.
> > So what does this look like in practice? Google engineering director Addy Osmani's breakdown of Claude Code Agent Teams is the best starting point. Use sub-agents for focused tasks and bring in full agent teams only when the work requires cross-domain coordination, keeping in mind that each teammate is a full Claude instance, which means a five-agent team burns 5x the tokens.
> > Start small, start now. Take your highest-traffic repo and write one AGENTS.md file defining ownership boundaries, verification rules, and handoff structure. Then run a Claude Code session against it and let the results tell you what to fix before scaling up. For the bigger picture, read Wharton Professor Ethan Mollick’s post on management as an AI superpower.
> >
> > IN THE KNOW
> > What’s trending on socials and headlines
> > Meme of the day
> >
> > • > > Dev Pep Talk: A veteran coder with 50 years of experience explains why AI won't make programmers obsolete.
> > • > > Agent Playbook: This engineer got 6 AI agents to autonomously operate a website in just two weeks. The full architecture and lessons are a goldmine for devs.
> > • > > Skill Up: Anthropic just dropped the complete guide to building skills for Claude. Try it to make your agents domain experts.
> > • > > Ship Faster: YCombinator’s CEO revealed his Claude Code prompt that allows him to build features with 4k+ lines of code in just one hour.
> >
> >
> >
> > • > > Claude Code adds Rewind feature for smarter coding sessions
> > • > > Peter Steinberger shares an 8-rule SOUL.md rewrite for OpenClaw that gives your AI coding assistant personality.
> > • > > Google shows devs how to build Recursive Language Models in ADK to handle 10M+ token contexts.
> > • > > xAI now offers up to 20% back in free API credits when you build on X.
> >
> >
> > AI CODING HACK
> > This hack builds n8n automations with a single prompt
> > Pro hack to build AI agents in n8n.
> > An AI engineer shared a setup that lets Claude Code build entire n8n workflows from a single prompt. Two open-source repos make this work.
> > Start by installing the n8n MCP server. This connects Claude Code to n8n's full node library (1,084 nodes) and your running instance:
> > claude mcp add n8n-mcp --scope user -- npx n8n-mcp
> > Add your n8n credentials to .mcp.json — your API URL and key. If you're running n8n locally, that's just http://localhost:5678.
> > Then install the n8n skills plugin. This teaches Claude how to write valid expressions, select the right node patterns, and catch errors before deployment:
> > /plugin install czlonkowski/n8n-skills
> > Restart Claude Code. Both activate automatically. Now write a prompt like this:
> > Build an n8n workflow that receives webhook form submissions, validates the email field, enriches the lead via LinkedIn, scores buying intent, and sends a summary to Slack and Notion.
> > Claude Code searches the node library, wires connections, sets parameters, validates everything, and creates it directly in your n8n instance.
> >
> > TOP & TRENDING RESOURCES
> > Today’s Spotlight
> > Click here to watch this tutorial.
> > Top Tutorial
> > How to use GPT-5.3-Codex for coding: OpenAI's latest coding model is a major step up for autonomous development. This tutorial covers how to steer the model during long tasks, use patch packages for cleaner dependency management, and have the agent write self-validating tests. You'll also see its "self-healing" generation in action, where it renders and compares its own output to catch mistakes mid-run.
> >
> > Top Repo
> > Shannon: An open‑source, fully autonomous AI hacker that hunts for attack vectors in code, then uses its built-in browser to execute real exploits, such as injection attacks, and auth bypass, to prove the vulnerability is actually exploitable.
> >
> > Trending Paper
> > Infrastructure noise in coding evals (by Anthropic): Hardware settings often secretly skew scores on AI coding tests. This study shows that simply increasing memory limits can boost performance by 6%, creating a gap larger than the difference between top models.
> >
> > Grow customers & revenue: Join companies like Google, IBM, and Datadog. Showcase your product to our 150K+ engineers and 100K+ followers on socials. Get in touch.
> >
> > Whenever you’re ready to take the next step
> >
> > • > > 10 Projects to Master AI Agents
> > • > > 100 Pro-Hacks for using Claude Code in 2026
> > • > > Top Resources to learn Claude Code in 2026
> > • > > Zero to Production Guide for Building AI Agents
> > • > > 200+ Resources to Become a Great Engineering Leader in 2026
> >
> >
> > What did you think of today's newsletter?
> > Your feedback helps us create better emails for you!
> > Loved it 🧠🧠🧠
> > Average 🧠🧠
> > It sucked 🧠
> > You can also reply directly to this email if you have suggestions, feedback, or questions.
> > Until next time — The Code team
> >
> >
> > Update your email preferences or unsubscribe here
> > © 2026 The Code
> > 228 Park Ave S, #29976, New York, New York 10003, United States
> > Terms of Service
