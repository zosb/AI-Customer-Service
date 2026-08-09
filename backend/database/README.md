# 数据库初始化脚本

本目录满足提交要求中的“建表语句 + 初始数据”。

- `schema.sql`：根据当前 SQLAlchemy ORM 模型生成的 MySQL 8 建表快照，便于代码评审。
- `seed.sql`：最小、无敏感信息的初始数据，只创建默认知识库，不创建测试账号或演示会话。

## 推荐初始化方式

正式开发/部署以 Alembic 为迁移真相源：

```cmd
python scripts\bootstrap_mysql.py
python -m alembic upgrade head
```

如面试官只希望直接审阅 SQL，可查看本目录。若直接在空数据库执行 SQL：

```cmd
mysql -u <user> -p <database> < database\schema.sql
mysql -u <user> -p <database> < database\seed.sql
```

不要在仓库中保存真实数据库密码。
