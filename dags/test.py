"""Quick scratchpad for testing STON.fi pools query.

Goal:
- verify endpoint POST /v1/pools/query
- verify payload format for sort_by (array vs string)
- print a small sample response
"""

from __future__ import annotations

import json
from typing import Any

import requests


def post_pools_query(sort_by: Any, limit: int = 20) -> dict[str, Any]:
    url = "https://api.ston.fi/v1/pools/query"
    payload: dict[str, Any] = {"sort_by": sort_by, "limit": limit}
    r = requests.post(url, json=payload, timeout=30)
    if r.status_code >= 400:
        # В 422 полезно увидеть тело ответа.
        try:
            body = r.json()
        except Exception:
            body = r.text
        raise RuntimeError(
            f"HTTP {r.status_code}. payload={json.dumps(payload)} response={body}"
        )

    data = r.json()
    if not isinstance(data, dict):
        raise TypeError(f"Expected JSON object, got: {type(data)}")
    return data


def main() -> None:
    # 1) Берем shortlist числовых полей из GET /v1/pools,
    # 2) перебираем sort_by=["<field>:asc|desc"],
    # 3) фиксируем первый успешный набор.

    print("Fetching GET /v1/pools to derive candidate sort fields...")
    r = requests.get("https://api.ston.fi/v1/pools", timeout=60)
    r.raise_for_status()
    all_pools = r.json()
    pool_list = all_pools.get("pool_list", [])
    print(f"GET pools: pool_list={len(pool_list)}")
    if not pool_list:
        raise RuntimeError("GET /v1/pools returned empty pool_list")

    # Забираем поля из первого пула и оставляем только правдоподобные для сортировки.
    sample = pool_list[0]
    possible_fields: list[str] = []
    for k, v in sample.items():
        if not isinstance(v, (str, int, float, type(None))):
            continue
        if any(
            token in k
            for token in [
                "tvl",
                "volume_24h_usd",
                "volume",
                "apy_",
                "lp_total_supply_usd",
                "lp_total_supply",
                "reserve",
            ]
        ):
            possible_fields.append(k)

    # Нормализуем и ограничиваем количество кандидатов.
    possible_fields = sorted(set(possible_fields))
    # Часто api использует не все поля; нам достаточно нескольких наиболее вероятных.
    preferred_order = [
        "lp_total_supply_usd",
        "tvl_usd",
        "volume_24h_usd",
        "volume_24h",
        "apy_1d",
        "apy_7d",
        "apy_30d",
        "lp_total_supply",
        "reserve0",
        "reserve1",
    ]
    preferred_fields = [f for f in preferred_order if f in possible_fields]
    other_fields = [f for f in possible_fields if f not in preferred_fields]
    candidate_fields = (preferred_fields + other_fields)[:15]

    print("Candidate sort fields:", candidate_fields)

    # Перебираем направления.
    directions = ["desc", "asc"]
    for field in candidate_fields:
        for direction in directions:
            sort_by = [f"{field}:{direction}"]
            print(f"\nTrying sort_by={json.dumps(sort_by)} (field={field})")
            try:
                data = post_pools_query(sort_by=sort_by, limit=20)
            except Exception as e:
                print(f"Request failed: {e}")
                continue

            pool_list = data.get("pool_list")
            if isinstance(pool_list, list):
                print(
                    f"SUCCESS: got pool_list={len(pool_list)} for sort_by={json.dumps(sort_by)}"
                )
                if pool_list:
                    print("Sample pool keys:", list(pool_list[0].keys()))
            else:
                print(
                    "SUCCESS but pool_list missing / not a list. Type=",
                    type(pool_list),
                )
            return

    raise RuntimeError("No valid sort_by found for candidates")


if __name__ == "__main__":
    main()
