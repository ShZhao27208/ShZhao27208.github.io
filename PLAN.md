# Personal Portfolio Website Plan

## TL;DR

> **Quick Summary**: 基于Jekyll+GitHub Pages的个人介绍网站，集成GitHub公开项目和ORCID学术论文数据
> 
> **Deliverables**: 
> - 个人简介页（年龄自动计算）
> - 学术论文展示（实时数据+统计）
> - GitHub项目展示（实时fork/star）
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 3 waves
> **Critical Path**: 配置 → GitHub API → ORCID API → 测试

---

## Context

### Original Request
用户需要一个个人介绍网站，托管在GitHub Pages (ShZhao27208.github.io)，包含三个板块：
1. 个人简介 - 手动更新
2. 学术 - 集成ORCID/WoS论文数据
3. GitHub - 实时展示公开项目

### ⚠️ Prerequisite Required
**用户需提供以下信息才能继续**:
- ORCID iD (用于学术论文展示)
- 出生日期或年龄 (用于年龄计算，如不愿提供可删除该功能)

### Tech Stack
- Jekyll (Ruby) + GitHub Pages
- Location: D:\self\ShZhao27208.github.io
- Hosting: FREE

### Research Findings

| 数据源 | API | 认证 | 备注 |
|--------|-----|------|------|
| GitHub | `GET /users/{username}/repos` | 不需要 | 60req/h |
| ORCID | `pub.orcid.org/v3.0/{iD}/works` | 不需要 | 公开记录 |
| WoS | Clarivate API | 需要订阅 | 用户补充数据 |

---

## Work Objectives

### Core Objective
创建功能完整的个人介绍网站，包含三个信息展示板块

### Concrete Deliverables
- [x] Jekyll基础结构
- [x] _config.yml 配置文件
- [x] 个人简介页面（含年龄计算JS）
- [x] 学术论文展示页（ORCID API）
- [x] GitHub项目展示页（REST API）
- [x] 自动化测试

### Definition of Done
- [ ] 三个板块页面均可访问
- [ ] GitHub API数据正确显示
- [ ] ORCID论文数据正确显示
- [ ] 年龄自动计算正确
- [ ] Playwright测试通过

### Must Have
- 响应式设计（移动端适配）
- API失败时的fallback显示
- 无数据时的占位提示

### Must NOT Have
- 不需要blog功能
- 不需要评论系统
- 不需要用户登录

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (existing repo)
- **Automated tests**: YES (Playwright)
- **Verify with**: 浏览器自动化测试

### QA Policy
每个任务通过Playwright验证页面渲染和数据加载

---

## Execution Strategy

### Wave 1 (Foundation)
- T1: Jekyll基础结构搭建
- T2: _config.yml配置模板
- T3: 创建个人配置文件 (config.yml)

### Wave 2 (Core Features)
- T4: 个人简介页面 (about.html)
- T5: GitHub API数据获取 (github.html)
- T6: ORCID API数据获取 (academic.html)

### Wave 3 (Integration & Testing)
- T7: CSS样式
- T8: 测试验证
- T9: 部署验证

---

---

## TODOs

### Wave 1: Foundation

- [ ] 1.1 Create Jekyll config file (_config.yml)

  **What to do**: Create _config.yml with basic settings (title, description, markdown config)

  **Acceptance Criteria**:
  - [ ] File exists
  - [ ] Valid YAML syntax

- [ ] 1.2 Create layout template (_layouts/default.html)

  **What to do**: Create HTML5 base layout with header, content, footer placeholders

  **Acceptance Criteria**:
  - [ ] Layout file exists
  - [ ] Proper HTML structure

### Wave 2: About Section

- [ ] 2.1 Create personal info config (_data/personal.yml)

  **What to do**: Create YAML config with user info fields (name, email, phone, qq, wechat, bio) - NOTE: birthdate is optional, delete if not provided

  **Acceptance Criteria**:
  - [ ] Config file exists with all fields

- [ ] 2.2 Create about page (about.html)

  **What to do**: Create about page with personal info display and JS age calculation (if birthdate provided)

  **Acceptance Criteria**:
  - [ ] Name displays
  - [ ] Age auto-calculates (if configured)
  - [ ] Contact info shows

### Wave 3: GitHub Section

- [ ] 3.1 GitHub API JavaScript (_includes/github-repo.js)

  **What to do**: Create JS to fetch repos from GitHub REST API (GET /users/ShZhao27208/repos)

  **Acceptance Criteria**:
  - [ ] API call succeeds
  - [ ] Returns repo data

- [ ] 3.2 Create GitHub page (github.html)

  **What to do**: Create page displaying repo list with description, stars, forks

  **Acceptance Criteria**:
  - [ ] Repos display
  - [ ] Stars/forks visible

### Wave 4: Academic Section

- [ ] 4.1 ORCID API JavaScript (_includes/orcid-api.js)

  **What to do**: Create JS to fetch publications from ORCID API (requires user ORCID iD)

  **Acceptance Criteria**:
  - [ ] Works fetch when ORCID provided

- [ ] 4.2 Create academic page (academic.html)

  **What to do**: Create page with paper list, author bolding for first/co-first, statistics

  **Acceptance Criteria**:
  - [ ] Papers display
  - [ ] Stats calculate (total, first/co-first count)

### Wave 5: Integration & Testing

- [ ] 5.1 CSS styling (main.css)

  **What to do**: Create responsive CSS for all three sections

  **Acceptance Criteria**:
  - [ ] Responsive design works
  - [ ] Clean appearance

- [ ] 5.2 Index page update (index.html)

  **What to do**: Create home page with navigation to all sections

  **Acceptance Criteria**:
  - [ ] Links work
  - [ ] Navigation clear

- [ ] 5.3 Playwright verification

  **What to do**: Run automated browser tests

  **Acceptance Criteria**:
  - [ ] All pages load
  - [ ] No critical errors

---

## Final Verification Wave

- [ ] F1. Plan Compliance Audit (oracle)
- [ ] F2. Code Quality Review (unspecified-high)
- [ ] F3. Real Manual QA (unspecified-high)
- [ ] F4. Scope Fidelity Check (deep)