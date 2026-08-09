from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.models.user import User


def list_users() -> None:
    with SessionLocal() as database:
        users = database.scalars(
            select(User).order_by(User.id)
        ).all()
        if not users:
            print("当前没有用户。")
            return
        print("ID   ROLE   STATUS     ACCOUNT                         DISPLAY_NAME")
        print("-" * 78)
        for user in users:
            account = user.email or user.phone or "-"
            print(
                f"{user.id:<4} {user.role:<6} {user.status:<10} "
                f"{account:<31} {user.display_name or '-'}"
            )


def set_role(user_id: int, role: str) -> None:
    with SessionLocal() as database:
        user = database.get(User, user_id)
        if user is None:
            raise SystemExit(f"用户不存在：id={user_id}")
        user.role = role
        database.commit()
        print(
            f"用户 id={user.id} ({user.email or user.phone or '-'}) "
            f"角色已更新为：{role}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI Customer Service 管理员角色工具"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出用户")

    grant = sub.add_parser("grant", help="授予管理员角色")
    grant.add_argument("--user-id", type=int, required=True)

    revoke = sub.add_parser("revoke", help="恢复普通用户角色")
    revoke.add_argument("--user-id", type=int, required=True)

    args = parser.parse_args()
    if args.command == "list":
        list_users()
    elif args.command == "grant":
        set_role(args.user_id, "admin")
    else:
        set_role(args.user_id, "user")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
