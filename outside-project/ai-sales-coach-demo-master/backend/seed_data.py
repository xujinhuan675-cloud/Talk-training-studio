# coding=utf-8
"""初始化种子数据：用户、分组、维度、场景、历史演练记录"""

import asyncio
import hashlib
import json
import random
import uuid
from datetime import datetime, timedelta

import aiosqlite

import config
from database import init_db

DB_PATH = config.DB_PATH


def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def _token(username: str) -> str:
    return hashlib.md5(f"demo-{username}-token".encode()).hexdigest()


GROUPS = [
    {"id": 1, "name": "美业1组"},
    {"id": 2, "name": "美业2组"},
    {"id": 3, "name": "管理组"},
]

USERS = [
    {"id": 1, "name": "管理员", "username": "admin",   "password": _md5("admin123"),   "role": "admin",   "group_id": 3},
    {"id": 2, "name": "组长李梅","username": "leader1", "password": _md5("leader123"),  "role": "leader",  "group_id": 1},
    {"id": 3, "name": "王小红",  "username": "user1",   "password": _md5("user123"),    "role": "staff",   "group_id": 1},
    {"id": 4, "name": "张小明",  "username": "user2",   "password": _md5("user123"),    "role": "staff",   "group_id": 1},
    {"id": 5, "name": "刘小丽",  "username": "user3",   "password": _md5("user123"),    "role": "staff",   "group_id": 2},
    {"id": 6, "name": "陈小强",  "username": "user4",   "password": _md5("user123"),    "role": "staff",   "group_id": 2},
]

DIMENSIONS = [
    {"id": 1, "name": "专业度",  "description": "是否能准确介绍产品/服务特点，给出有依据的专业回答，避免夸大或违规承诺"},
    {"id": 2, "name": "亲和力",  "description": "是否能建立良好的对话氛围，让客户感受到被理解和尊重，避免机械推销感"},
    {"id": 3, "name": "应变力",  "description": "能否有效处理客户异议、竞品比较、价格压力等挑战性场景，给出合适应对"},
    {"id": 4, "name": "成交力",  "description": "能否识别客户购买信号，在合适时机自然推动成交，不强推、不错失机会"},
]

SCENARIOS = [
    {
        "id": 1,
        "name": "新客推介 - 美甲套餐",
        "difficulty": 1,
        "persona": "30岁女性，上班族，首次到店，对美甲感兴趣但预算有限，偏爱性价比高的方案",
        "scene_desc": "客户进店咨询美甲套餐，你是美甲店的销售顾问，目标是了解客户需求并推荐合适套餐",
        "opening": "你好，我看到门口说有新客优惠，能介绍一下吗？",
        "is_required": 1,
        "dimensions": [{"id": 1, "weight": 30}, {"id": 2, "weight": 30}, {"id": 3, "weight": 20}, {"id": 4, "weight": 20}],
    },
    {
        "id": 2,
        "name": "续卡挽留 - 到期提醒",
        "difficulty": 2,
        "persona": "35岁女性，老客户，购买了年卡还有2次未用，近期较忙较少来店，对续卡持观望态度",
        "scene_desc": "客户年卡即将到期还有2次未使用，主动联系客户续卡，目标是推动续卡并预约使用剩余次数",
        "opening": "喂，你们店打来的吗？",
        "is_required": 1,
        "dimensions": [{"id": 1, "weight": 20}, {"id": 2, "weight": 30}, {"id": 3, "weight": 30}, {"id": 4, "weight": 20}],
    },
    {
        "id": 3,
        "name": "价格异议 - 套餐对比",
        "difficulty": 2,
        "persona": "28岁女性，有过美容消费经验，看过竞品价格，认为我们店比隔壁店贵，想要压价或获得更多优惠",
        "scene_desc": "客户正在比较不同美容店的套餐价格，质疑我们的定价，你需要解释价值差异并维护价格",
        "opening": None,
        "is_required": 1,
        "dimensions": [{"id": 1, "weight": 35}, {"id": 2, "weight": 25}, {"id": 3, "weight": 30}, {"id": 4, "weight": 10}],
    },
    {
        "id": 4,
        "name": "退费挽留 - 情绪安抚",
        "difficulty": 3,
        "persona": "40岁女性，购买了护肤疗程套餐，做了2次感觉效果不明显，情绪较激动，明确要求退款",
        "scene_desc": "客户对服务效果不满意要求退款，情绪激动，你需要安抚情绪、了解问题根源，争取给出解决方案避免退款",
        "opening": "我要退款！做了两次一点效果都没有，你们当初怎么说的？",
        "is_required": 1,
        "dimensions": [{"id": 1, "weight": 25}, {"id": 2, "weight": 35}, {"id": 3, "weight": 30}, {"id": 4, "weight": 10}],
    },
    {
        "id": 5,
        "name": "VIP 转化 - 高端升级",
        "difficulty": 3,
        "persona": "38岁女性，忠实老客户，已消费多次，对店面信任度较高，但对高端VIP卡价格有顾虑，需要充分说服",
        "scene_desc": "向老客户推荐升级VIP钻石卡（价值5888元），她有意向但犹豫价格，你需要展示价值并促成决策",
        "opening": None,
        "is_required": 0,
        "dimensions": [{"id": 1, "weight": 30}, {"id": 2, "weight": 20}, {"id": 3, "weight": 20}, {"id": 4, "weight": 30}],
    },
    {
        "id": 6,
        "name": "舆情应对 - 网络差评",
        "difficulty": 4,
        "persona": "32岁女性，在社交媒体上看到关于本店的负面评价，带着质疑心态进店咨询，戒备心强",
        "scene_desc": "客户看到网络负面评价后进店，对店面持怀疑态度，你需要正面回应，重建信任",
        "opening": "我在大众点评看到有人说你们这里服务很差，是真的吗？",
        "is_required": 0,
        "dimensions": [{"id": 1, "weight": 25}, {"id": 2, "weight": 35}, {"id": 3, "weight": 30}, {"id": 4, "weight": 10}],
    },
]


async def _seed_groups(db):
    for g in GROUPS:
        await db.execute(
            "INSERT OR IGNORE INTO groups(id, name) VALUES(?, ?)",
            (g["id"], g["name"])
        )


async def _seed_users(db):
    for u in USERS:
        token = _token(u["username"])
        await db.execute(
            """INSERT OR IGNORE INTO users(id, name, username, password, role, group_id, token)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (u["id"], u["name"], u["username"], u["password"], u["role"], u["group_id"], token)
        )


async def _seed_dimensions(db):
    for d in DIMENSIONS:
        await db.execute(
            """INSERT OR IGNORE INTO training_dimension(id, name, description, status)
               VALUES(?, ?, ?, 1)""",
            (d["id"], d["name"], d["description"])
        )


async def _seed_scenarios(db):
    for sc in SCENARIOS:
        await db.execute(
            """INSERT OR IGNORE INTO training_scenario
               (id, name, difficulty, persona, scene_desc, opening, is_required, status)
               VALUES(?, ?, ?, ?, ?, ?, ?, 1)""",
            (sc["id"], sc["name"], sc["difficulty"], sc["persona"],
             sc["scene_desc"], sc["opening"], sc["is_required"])
        )
        # 场景-维度关联（先删旧，再插新，保证幂等）
        await db.execute("DELETE FROM scenario_dimension WHERE scenario_id=?", (sc["id"],))
        for dim in sc["dimensions"]:
            await db.execute(
                "INSERT INTO scenario_dimension(scenario_id, dimension_id, weight) VALUES(?,?,?)",
                (sc["id"], dim["id"], dim["weight"])
            )


async def _seed_history(db):
    """生成 60 条历史演练记录（随机分配给各用户）"""
    staff_users = [u for u in USERS if u["role"] == "staff"]
    required_scenarios = [sc for sc in SCENARIOS if sc["is_required"] == 1]
    all_scenarios = SCENARIOS

    base_time = datetime.now() - timedelta(days=30)
    seq = 0

    for user in staff_users:
        # 确保每个员工都完成了所有必练场景（支持排行榜入榜）
        for sc in required_scenarios:
            seq += 1
            session_id = str(uuid.uuid4())
            created_at = base_time + timedelta(hours=seq * 3)
            ended_at = created_at + timedelta(minutes=random.randint(5, 20))
            duration_sec = int((ended_at - created_at).total_seconds())
            total_score = random.randint(55, 95)

            await db.execute(
                """INSERT OR IGNORE INTO training_session
                   (session_id, user_id, scenario_id, status, duration_sec, message_count, created_at, ended_at)
                   VALUES(?,?,?,2,?,?,?,?)""",
                (session_id, user["id"], sc["id"], duration_sec, random.randint(4, 14),
                 created_at.strftime("%Y-%m-%d %H:%M:%S"),
                 ended_at.strftime("%Y-%m-%d %H:%M:%S"))
            )

            # 生成对应评分
            dim_scores = []
            for dim_ref in sc["dimensions"]:
                dim_obj = next(d for d in DIMENSIONS if d["id"] == dim_ref["id"])
                score = max(40, min(100, total_score + random.randint(-15, 15)))
                dim_scores.append({
                    "dimension_id": dim_obj["id"],
                    "dimension_name": dim_obj["name"],
                    "score": score,
                    "comment": f"证据：销售在对话中展示了基本的{dim_obj['name']}；结论：总体表现一般，给 {score} 分",
                })

            await db.execute(
                """INSERT OR IGNORE INTO training_score
                   (session_id, total_score, dimension_scores, summary, highlights, suggestions, status)
                   VALUES(?,?,?,?,?,?,1)""",
                (
                    session_id,
                    total_score,
                    json.dumps(dim_scores, ensure_ascii=False),
                    f"本次演练整体表现{'良好' if total_score >= 80 else '一般'}，需在细节上继续打磨。",
                    json.dumps(["能够准确介绍产品信息", "对客户情绪有所感知"], ensure_ascii=False),
                    json.dumps(["建议加强异议处理的主动性", "成交时机的把握还需提升"], ensure_ascii=False),
                )
            )

        # 随机多练 2 条其他场景
        for sc in random.sample(all_scenarios, min(2, len(all_scenarios))):
            seq += 1
            session_id = str(uuid.uuid4())
            created_at = base_time + timedelta(hours=seq * 3 + 1)
            ended_at = created_at + timedelta(minutes=random.randint(3, 15))
            duration_sec = int((ended_at - created_at).total_seconds())
            total_score = random.randint(50, 92)

            await db.execute(
                """INSERT OR IGNORE INTO training_session
                   (session_id, user_id, scenario_id, status, duration_sec, message_count, created_at, ended_at)
                   VALUES(?,?,?,2,?,?,?,?)""",
                (session_id, user["id"], sc["id"], duration_sec, random.randint(4, 12),
                 created_at.strftime("%Y-%m-%d %H:%M:%S"),
                 ended_at.strftime("%Y-%m-%d %H:%M:%S"))
            )
            dim_scores = []
            for dim_ref in sc["dimensions"]:
                dim_obj = next(d for d in DIMENSIONS if d["id"] == dim_ref["id"])
                score = max(40, min(100, total_score + random.randint(-15, 15)))
                dim_scores.append({
                    "dimension_id": dim_obj["id"],
                    "dimension_name": dim_obj["name"],
                    "score": score,
                    "comment": f"证据：销售基本完成了{dim_obj['name']}相关动作；结论：给 {score} 分",
                })
            await db.execute(
                """INSERT OR IGNORE INTO training_score
                   (session_id, total_score, dimension_scores, summary, highlights, suggestions, status)
                   VALUES(?,?,?,?,?,?,1)""",
                (
                    session_id,
                    total_score,
                    json.dumps(dim_scores, ensure_ascii=False),
                    f"表现{'不错' if total_score >= 75 else '有待提高'}，继续加油。",
                    json.dumps(["表现积极", "沟通较流畅"], ensure_ascii=False),
                    json.dumps(["多练习异议处理", "注意成交节奏"], ensure_ascii=False),
                )
            )


async def run():
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await _seed_groups(db)
        await _seed_users(db)
        await _seed_dimensions(db)
        await _seed_scenarios(db)
        await _seed_history(db)
        await db.commit()
    print("种子数据初始化完成！")
    print("\n演示账号：")
    print("  管理员：admin / admin123")
    print("  组长：  leader1 / leader123")
    print("  员工：  user1~user4 / user123")


if __name__ == "__main__":
    asyncio.run(run())
