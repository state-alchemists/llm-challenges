import asyncio

async def main():
    await asyncio.sleep(1)
    print('Async OK')

asyncio.run(main())