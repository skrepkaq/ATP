import asyncio
import os

from playwright.async_api import async_playwright
from TikTokApi import TikTokApi
from TikTokApi.exceptions import EmptyResponseException
from TikTokApi.helpers import random_choice


BROWSERLESS_URL = os.getenv("BROWSERLESS_URL", "ws://localhost:3000")


class CDPTikTokApi(TikTokApi):
    async def create_sessions(
        self,
        cdp_url,
        num_sessions=5,
        ms_tokens=None,
        proxies=None,
        sleep_after=1,
        starting_url="https://www.tiktok.com",
        context_options={},
        cookies=None,
        suppress_resource_load_types=None,
        timeout=30000,
    ):
        """
        Extends TikTokApi.create_sessions with connect_over_cdp.
        """
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.connect_over_cdp(
            cdp_url + '?launch={"stealth": true}'
        )

        await asyncio.gather(
            *(
                self._TikTokApi__create_session(
                    proxy=random_choice(proxies),
                    ms_token=random_choice(ms_tokens),
                    url=starting_url,
                    context_options=context_options,
                    sleep_after=sleep_after,
                    cookies=random_choice(cookies),
                    suppress_resource_load_types=suppress_resource_load_types,
                    timeout=timeout,
                )
                for _ in range(num_sessions)
            )
        )


async def get_token():
    async with CDPTikTokApi() as api:
        await api.create_sessions(
            cdp_url=BROWSERLESS_URL,
            ms_tokens=[None],
            num_sessions=1,
            sleep_after=3
        )
        ms_token = api._get_session()[1].ms_token

        print("Generated token:")
        print(ms_token)

        return ms_token


async def test_token(ms_token):
    async with CDPTikTokApi() as api:
        await api.create_sessions(
            cdp_url=BROWSERLESS_URL,
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3
        )
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
