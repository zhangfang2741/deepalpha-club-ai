"""账号删除的级联顺序单元测试。

App Store 审核指南 5.1.1(v) 要求有注册功能的 App 必须能在 App 内自助删除账号，
且要删干净。vocabulary_* 几张表只声明了 foreign_key、没有 ON DELETE CASCADE，
所以顺序错了会直接撞外键约束——这组测试锁住删除顺序。
"""

import uuid
from unittest.mock import AsyncMock

from app.services.vocabulary.users import delete_user


async def test_delete_user_removes_all_tables_in_fk_safe_order():
    """子表必须先于父表删除，否则外键约束报错。"""
    session = AsyncMock()
    user_id = uuid.uuid4()

    await delete_user(session, user_id)

    statements = [str(call.args[0]) for call in session.execute.await_args_list]
    assert len(statements) == 5

    # 依赖顺序：关联表 → 日志 → 歌单 → 单词 → 用户
    assert "DELETE FROM vocabulary_playlist_items" in statements[0]
    assert "DELETE FROM vocabulary_review_logs" in statements[1]
    assert "DELETE FROM vocabulary_playlists" in statements[2]
    assert "DELETE FROM vocabulary_words" in statements[3]
    assert "DELETE FROM vocabulary_users" in statements[4]


async def test_delete_user_commits_once_so_deletion_is_atomic():
    """五张表必须在同一个事务里，中途失败不能留下删了一半的账号。"""
    session = AsyncMock()

    await delete_user(session, uuid.uuid4())

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


async def test_delete_user_scopes_playlist_items_by_both_playlist_and_word():
    """歌单条目同时外键到 playlist 和 word，两条路径都要清，否则删单词时撞约束。"""
    session = AsyncMock()

    await delete_user(session, uuid.uuid4())

    playlist_items_stmt = str(session.execute.await_args_list[0].args[0])
    assert "playlist_id IN" in playlist_items_stmt
    assert "word_id IN" in playlist_items_stmt


async def test_delete_user_never_touches_other_users_rows():
    """每条 DELETE 都必须带 user_id / 子查询限定，绝不能出现无条件删表。"""
    session = AsyncMock()

    await delete_user(session, uuid.uuid4())

    for call in session.execute.await_args_list:
        statement = str(call.args[0])
        assert "WHERE" in statement, f"存在无条件 DELETE：{statement}"
