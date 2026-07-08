# 网络舆情事件智能分析系统开发协作说明-简化版

## 一、项目成员分工

本项目采用 GitHub 进行多人协作开发，每位成员负责不同模块。

项目分支：

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


# 二、GitHub代码同步流程

## 第一次加入项目

下载项目：

```bash
git clone 项目地址
```

进入项目：

```bash
cd network-public-opinion-system
```

查看分支：

```bash
git branch -a
```

切换自己的开发分支：

例如前端：

```bash
git checkout frontend
```

---

# 三、每天开始开发前

先获取最新代码：

```bash
git pull
```

作用：

> 将 GitHub 上最新代码同步到本地，避免代码版本不一致。

推荐流程：

```
打开项目

↓

git pull

↓

开始开发
```

---

# 四、完成代码后提交

查看修改：

```bash
git status
```

添加代码：

```bash
git add .
```

提交：

```bash
git commit -m "完成xxx功能"
```

上传：

```bash
git push
```

---

# 五、代码合并流程

个人开发分支：

```
frontend
backend
crawler
analysis
ai_service
```

完成开发后：

提交 Pull Request

合并到：

```
dev
```

所有功能测试完成后：

```
dev
 ↓
main
```

---

# 六、注意事项

1. 不要直接修改 main 分支。

2. 每个人只修改自己负责的模块。

3. 开始开发前先执行：

```bash
git pull
```

4. 提交代码时写清楚修改内容。

例如：

推荐：

```
完成用户登录接口
增加事件列表页面
优化情感分析模型
```

不要：

```
修改
test
111
```
