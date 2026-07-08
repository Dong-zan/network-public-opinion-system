# GitHub团队协作说明（新手入门版）-详细版

## 1. 为什么使用 GitHub？

本项目是多人合作开发：

> 网络舆情事件智能分析系统

项目包含：

* 前端页面
* 后端接口
* 爬虫系统
* AI分析模型
* 大模型问答

多人同时修改代码，如果直接互相发送文件，会出现：

* 文件版本混乱
* 不知道谁修改了什么
* 代码覆盖
* 无法恢复旧版本

因此使用 GitHub 管理代码。

---

# 2. Git、GitHub分别是什么？

## Git

Git 是一个代码版本管理工具。

作用：

记录：

* 谁修改了代码
* 修改了什么
* 什么时间修改
* 可以恢复以前版本

例如：

今天：

```
登录页面 V1
```

修改后：

```
登录页面 V2
```

Git 可以保存两个版本。

---

## GitHub

GitHub 是存放 Git 项目的网站。

简单理解：

```
Git = 本地管理工具

GitHub = 云端代码仓库
```

关系：

```
电脑本地项目

      ↑↓

     Git

      ↑↓

   GitHub仓库
```

---

# 3. 非常重要：分支是什么？

很多新人容易误解：

❌ 错误理解：

```
dev
 |
 ├── frontend
 └── backend
```

认为：

frontend 是 dev 文件夹里的东西。

正确理解：

Git 分支不是文件夹。

它们是：

```
        main
          |
         dev
       /  |   \
      /   |    \
 frontend backend crawler
```

表示：

不同的人在不同版本线上开发。

---

# 4. 本项目分支说明

当前项目分支：

```
main
 |
 dev
 |
 ├── frontend
 ├── backend
 ├── crawler
 ├── analysis
 └── ai_service
```

| 分支         | 用途     | 负责人  |
| ---------- | ------ | ---- |
| main       | 最终稳定版本 | 组长   |
| dev        | 开发整合版本 | 所有成员 |
| frontend   | 前端开发   | 前端成员 |
| backend    | 后端开发   | 后端成员 |
| crawler    | 爬虫开发   | 爬虫成员 |
| analysis   | 算法分析   | 算法成员 |
| ai_service | AI服务   | AI成员 |

---

# 5. 开发原则

## 原则1：不要直接修改main

main代表：

```
最终可运行版本
```

任何人不要：

```
git checkout main
```

然后写代码。

---

## 原则2：每个人只修改自己的模块

例如：

前端：

```
frontend/
```

后端：

```
backend/
```

爬虫：

```
crawler/
```

不要随便修改别人负责的目录。

---

## 原则3：每天提交代码

不要：

两周写完一次，然后一次提交。

推荐：

每天：

```
完成一个功能
↓
提交一次
```

---

# 6. 第一次加入项目操作流程

## 第一步：安装 Git

下载：

[https://git-scm.com/](https://git-scm.com/)

安装完成后测试：

打开 PowerShell：

输入：

```bash
git --version
```

如果显示：

```
git version xxx
```

说明安装成功。

---

# 7. 下载项目到电脑

打开 PowerShell。

进入想保存的位置：

例如：

```powershell
cd Desktop
```

复制 GitHub 仓库地址：

GitHub：

```
Code
 ↓
HTTPS
 ↓
复制地址
```

执行：

```powershell
git clone 仓库地址
```

例如：

```powershell
git clone https://github.com/xxx/network-public-opinion-system.git
```

成功后：

电脑出现：

```
network-public-opinion-system
```

---

进入项目：

```powershell
cd network-public-opinion-system
```

---

# 8. 查看当前分支

输入：

```powershell
git branch
```

显示：

```
* main
  dev
```

其中：

```
*
```

代表当前所在分支。

---

# 9. 切换到自己的开发分支

例如：

## 前端成员

```powershell
git checkout frontend
```

## 后端成员

```powershell
git checkout backend
```

## 爬虫成员

```powershell
git checkout crawler
```

## 算法成员

```powershell
git checkout analysis
```

## AI成员

```powershell
git checkout ai_service
```

成功：

```
Switched to branch xxx
```

---

# 10. 每次开始开发前

必须执行：

```powershell
git pull
```

作用：

从 GitHub 获取最新代码。

流程：

```
打开电脑

↓

进入项目

↓

git pull

↓

开始写代码
```

---

# 11. 修改代码

正常使用：

* VS Code
* PyCharm
* WebStorm

例如：

修改：

```
frontend/src/App.vue
```

保存。

---

# 12. 查看修改

输入：

```powershell
git status
```

例如：

显示：

```
modified:
frontend/src/App.vue
```

说明：

这个文件被修改。

---

# 13. 提交代码到本地 Git

## 第一步：添加修改

```powershell
git add .
```

意思：

告诉 Git：

“我要保存这些修改”。

---

## 第二步：提交

```powershell
git commit -m "完成登录页面"
```

格式：

```
git commit -m "说明本次修改内容"
```

推荐：

好的：

```
完成用户登录接口
增加事件详情页面
优化情感分析模型
```

不要：

```
修改
test
111
```

---

## 第三步：上传 GitHub

```powershell
git push
```

完成。

此时：

电脑代码

↓

GitHub仓库

同步。

---

# 14. 一次完整开发流程

以后每天：

```
1. 打开项目

↓

2. 查看分支

git branch


↓

3. 更新代码

git pull


↓

4. 开发功能


↓

5. 查看修改

git status


↓

6. 添加

git add .


↓

7. 提交

git commit -m "完成xxx"


↓

8. 上传

git push
```

---

# 15. 如何合并代码？

普通成员：

不负责合并。

完成任务后：

告诉组长：

```
我的功能完成，可以合并
```

---

组长操作：

例如合并前端代码。

切换：

```powershell
git checkout dev
```

更新：

```powershell
git pull
```

合并：

```powershell
git merge frontend
```

成功后：

前端代码进入：

```
dev
```

---

# 16. dev和main关系

开发流程：

```
个人分支

frontend
backend
crawler
analysis
ai_service


        ↓


       dev


        ↓


     测试完成


        ↓


       main
```

解释：

* 个人分支：写代码
* dev：大家代码集合
* main：最终版本

---

# 17. 常见问题

## 问题1：

```
fatal: not a git repository
```

原因：

当前目录不是项目目录。

解决：

进入：

```
network-public-opinion-system
```

例如：

```powershell
cd network-public-opinion-system
```

---

## 问题2：

GitHub看不到新建文件夹

原因：

Git不保存空文件夹。

解决：

创建：

```
.gitkeep
```

例如：

```
frontend/.gitkeep
```

---

## 问题3：

提交失败

先：

```powershell
git pull
```

再：

```powershell
git push
```

---

## 问题4：

出现：

```
CONFLICT
```

表示：

代码冲突。

不要强行解决。

联系负责人处理。

---

# 18. 不允许做的事情

## 禁止1：

不要上传大文件：

例如：

```
模型文件
视频
大量数据
node_modules
```

---

## 禁止2：

不要提交密码

例如：

不要上传：

```
.env
API_KEY
数据库密码
```

---

## 禁止3：

不要删除别人分支

不要执行：

```bash
git branch -D xxx
```

---

# 19. 项目目录规范

最终：

```
network-public-opinion-system

├── frontend
│
├── backend
│
├── crawler
│
├── analysis
│
├── ai_service
│
├── docs
│
└── README.md
```

说明：

| 目录         | 内容        |
| ---------- | --------- |
| frontend   | Vue前端     |
| backend    | FastAPI后端 |
| crawler    | 爬虫程序      |
| analysis   | 算法模型      |
| ai_service | 大模型接口     |
| docs       | 项目文档      |

---

# 20. 提交信息规范

格式：

```
类型: 内容
```

例如：

```
feat: 完成用户登录

feat: 添加热点事件接口

fix: 修复数据解析错误

docs: 更新项目文档
```

---

# 21. 最终记住这句话

## GitHub不是共享文件夹

不要想着：

```
我创建文件夹 → GitHub自动出现
```

正确流程：

```
本地修改

↓

git add

↓

git commit

↓

git push

↓

GitHub更新
```

---

## 新成员只需要记住4个命令：

每天：

```bash
git pull
```

提交：

```bash
git add .
git commit -m "说明"
git push
```

掌握这几个命令，就可以完成本项目全部协作开发。
