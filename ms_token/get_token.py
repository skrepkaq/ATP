import asyncio

from TikTokApi import TikTokApi
from TikTokApi.exceptions import EmptyResponseException


async def user_example():
    async with TikTokApi() as api:
        await api.create_sessions(ms_tokens=[None], num_sessions=1, sleep_after=3, browser="chromium", headless=False)
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
    asyncio.run(user_example())
