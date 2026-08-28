import { chromium } from "playwright";

const productionUrl = process.env.PRODUCTION_API_URL || "https://fastapi-sample.fastapicloud.dev/api";
const expectedVersion = (
  process.env.EXPECTED_VERSION ||
  process.env.EXPECTED_MASTER_VERSION ||
  ""
).trim();

if (!/^\d+\.\d+\.\d+$/.test(expectedVersion)) {
  throw new Error(`EXPECTED_VERSION must be a semantic version, got ${JSON.stringify(expectedVersion)}`);
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const response = await page.goto(productionUrl, {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  });

  if (!response) {
    throw new Error(`No HTTP response received from ${productionUrl}`);
  }
  if (!response.ok()) {
    throw new Error(`Production UI returned HTTP ${response.status()} for ${productionUrl}`);
  }

  const versionText = (await page.locator(".hero .subtitle").innerText()).trim();
  const match = versionText.match(/\b(\d+\.\d+\.\d+)\b/);
  if (!match) {
    throw new Error(`Could not extract the production version from ${JSON.stringify(versionText)}`);
  }

  const deployedVersion = match[1];
  console.log(`Production UI version: ${deployedVersion}`);
  console.log(`Expected source version: ${expectedVersion}`);

  if (deployedVersion !== expectedVersion) {
    throw new Error(
      `Production deployment drift: UI reports ${deployedVersion}, but source declares ${expectedVersion}`,
    );
  }
} finally {
  await browser.close();
}
