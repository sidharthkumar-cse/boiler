import puppeteer from 'puppeteer';
(async () => {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle0' });
  // Click on "Analytics"
  const tabs = await page.$$('button');
  for (const tab of tabs) {
    const text = await page.evaluate(el => el.textContent, tab);
    if (text === 'Analytics') {
      await tab.click();
      break;
    }
  }
  await page.waitForTimeout(1000);
  await page.screenshot({ path: 'analytics_full.png', fullPage: true });
  await browser.close();
})();
