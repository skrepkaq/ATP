import asyncio
import os
import json
from TikTokApi import TikTokApi
from TikTokApi.exceptions import EmptyResponseException

BROWSERLESS_URL = os.getenv("BROWSERLESS_URL")
LAUNCH_OPTIONS = {
    "headless": False,
    "stealth": True,
}


async def get_token():
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[None], num_sessions=1, sleep_after=5, connect_over_cdp=f"{BROWSERLESS_URL}?launch={json.dumps(LAUNCH_OPTIONS)}"
        )
        ms_token = api._get_session()[1].ms_token

        print("Generated token:")
        print(ms_token)

        return ms_token

async def test_token(ms_token):
    async with TikTokApi() as api:
        await api.create_sessions(ms_tokens=[ms_token], num_sessions=1, sleep_after=5, connect_over_cdp=f"{BROWSERLESS_URL}?launch={json.dumps(LAUNCH_OPTIONS)}")
        ms_token = api._get_session()[1].ms_token

        print("Generated token:")
        print(ms_token)

        print("Checking token...")
        try:
            await api.user("therock").info()
        except EmptyResponseException as e:
            print("Token is bad(")
            print(e)
        else:
            print("Token is ok!")


if __name__ == "__main__":
    print("Getting token...")
    ms_token = asyncio.run(get_token())
    if ms_token:
        print(f"\nms_token: {ms_token}")
        asyncio.run(test_token(ms_token))
    else:
        print("\nms_token not found")
