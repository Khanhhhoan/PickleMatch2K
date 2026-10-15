/**
 * Kiểm thử đầu-cuối qua trình duyệt cho các luồng chính của PickleMatch2K:
 * người chơi đặt sân - cọc - mở phòng - hủy, người chơi khác tham gia phòng, nhân viên xử lý tại quầy,
 * chủ sân cấu hình, quản trị viên giám sát.
 *
 * Chuẩn bị (trên CSDL demo/thử nghiệm, KHÔNG chạy trên dữ liệu thật vì script tạo và hủy đơn):
 *   - backend ở :8000, đã nạp dữ liệu demo (python manage.py seed) và SEPAY_SIMULATOR_ENABLED=true
 *   - frontend ở :3000 (npm run build && npm start), admin-portal ở :3001
 *
 *   node scripts/e2e_smoke.js            # chạy ngầm
 *   node scripts/e2e_smoke.js --show     # mở cửa sổ trình duyệt để quan sát
 *
 * Puppeteer không phải dependency của dự án. Cài một lần: npm install -g puppeteer
 * (hoặc đặt biến PUPPETEER_MODULE trỏ tới thư mục module puppeteer có sẵn trên máy).
 */
const fs = require("fs");
const path = require("path");

function loadPuppeteer() {
  const globalModules = path.join(process.env.APPDATA || "", "npm/node_modules");
  const candidates = [
    process.env.PUPPETEER_MODULE,
    "puppeteer",
    path.join(globalModules, "puppeteer"),
    path.join(globalModules, "@modelcontextprotocol/server-puppeteer/node_modules/puppeteer"),
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (err) {
      if (err.code !== "MODULE_NOT_FOUND") throw err;
    }
  }
  console.error("Không tìm thấy puppeteer. Cài bằng: npm install -g puppeteer (hoặc đặt biến PUPPETEER_MODULE).");
  process.exit(2);
}

const puppeteer = loadPuppeteer();

const WEB = process.env.E2E_WEB_URL || "http://localhost:3000";
const ADMIN = process.env.E2E_ADMIN_URL || "http://localhost:3001";
const PASSWORD = process.env.E2E_PASSWORD || "123456";
const API = process.env.E2E_API_URL || "http://localhost:8000/api/v1";
const SHOTS = path.join(__dirname, "../test-results/screenshots");
const TIMEOUT = 15000;
// Ảnh PNG 1x1 dùng làm chứng từ chuyển hoàn trong bước của nhân viên
const TINY_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

const results = [];
const problems = []; // lỗi JavaScript trên trang và phản hồi 5xx của API
let browser;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function newSession(label) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setViewport({ width: 1366, height: 900 });
  page.setDefaultTimeout(TIMEOUT);
  page.on("pageerror", (err) => problems.push(`[${label}] lỗi trang: ${err.message}`));
  page.on("response", (res) => {
    if (res.status() >= 500) problems.push(`[${label}] ${res.status()} ${res.request().method()} ${res.url()}`);
  });
  page.on("dialog", (dialog) => dialog.accept(dialog.type() === "prompt" ? "Kiểm thử tự động" : undefined));
  return { context, page, label };
}

// So khớp không phân biệt hoa thường: innerText phản ánh cả CSS text-transform (tiêu đề in hoa).
const waitForText = (page, text, timeout = TIMEOUT) =>
  page.waitForFunction((t) => document.body.innerText.toLowerCase().includes(t), { timeout }, text.toLowerCase());

const hasText = (page, text) => page.evaluate((t) => document.body.innerText.toLowerCase().includes(t), text.toLowerCase());

/**
 * Nhãn độ phù hợp trên thẻ phòng có tên chủ phòng cho trước: true = "Rất hợp với bạn" (phòng được đề xuất),
 * false = chỉ có "Độ phù hợp x%", null = thẻ không có độ phù hợp.
 */
const roomIsRecommended = (page, memberName) =>
  page.evaluate((name) => {
    const cards = [...document.querySelectorAll("div")].filter(
      (el) => el.querySelector("h3") && (el.innerText || "").includes(name) && (el.innerText || "").includes("Xin Tham Gia"),
    );
    const card = cards[cards.length - 1]; // khối nhỏ nhất có tiêu đề cụm sân, tên chủ phòng và nút tham gia = thẻ phòng
    if (!card) return null;
    const text = card.innerText.toLowerCase();
    if (text.includes("rất hợp với bạn")) return true;
    return text.includes("độ phù hợp ") ? false : null;
  }, memberName);

/**
 * Bấm phần tử khớp selector có chứa đoạn chữ (bỏ qua phần tử bị vô hiệu hóa), chờ tới khi nó xuất hiện.
 * within: chỉ tìm trong khối nhỏ nhất chứa đoạn chữ này. exact: chữ trên nút phải trùng hoàn toàn.
 */
async function clickText(page, selector, text, { within = null, index = 0, exact = false } = {}) {
  const tryClick = () =>
    page.evaluate(
      (sel, t, scopeText, i, isExact) => {
        const textOf = (el) => (el.innerText || "").trim().toLowerCase();
        const fits = (el) => (isExact ? textOf(el) === t : textOf(el).includes(t));
        let scope = document;
        if (scopeText) {
          const containers = [...document.querySelectorAll("div, li, tr")].filter((el) => textOf(el).includes(scopeText));
          scope = containers.reverse().find((el) => [...el.querySelectorAll(sel)].some(fits));
          if (!scope) return false;
        }
        const matches = [...scope.querySelectorAll(sel)].filter((el) => fits(el) && !el.disabled);
        if (!matches[i]) return false;
        matches[i].scrollIntoView({ block: "center" });
        matches[i].click();
        return true;
      },
      selector, text.toLowerCase(), within ? within.toLowerCase() : null, index, exact,
    );

  const deadline = Date.now() + TIMEOUT;
  while (Date.now() < deadline) {
    if (await tryClick()) return;
    await sleep(250);
  }
  throw new Error(`Không tìm thấy "${text}" (${selector})${within ? ` trong khối chứa "${within}"` : ""}`);
}

/** Điền giá trị vào ô nhập có nhãn chứa đoạn chữ cho trước. */
async function fillByLabel(page, labelText, value) {
  const handle = await page.evaluateHandle((t) => {
    const label = [...document.querySelectorAll("label")].reverse().find((l) => l.innerText.toLowerCase().includes(t.toLowerCase()));
    if (!label) return null;
    return label.querySelector("input, textarea, select") || label.parentElement.querySelector("input, textarea, select");
  }, labelText);
  const element = handle.asElement();
  if (!element) throw new Error(`Không tìm thấy ô nhập có nhãn "${labelText}"`);
  await element.click({ clickCount: 3 });
  await element.type(String(value));
}

async function login(session, baseUrl, email) {
  const { page } = session;
  await page.goto(`${baseUrl}/login`, { waitUntil: "networkidle2" });
  await page.type('input[type="email"]', email);
  await page.type('input[type="password"]', PASSWORD);
  await Promise.all([
    page.waitForFunction(() => !location.pathname.startsWith("/login"), { timeout: TIMEOUT }),
    page.click('button[type="submit"]'),
  ]);
}

async function step(session, name, fn) {
  const started = Date.now();
  try {
    await fn(session.page);
    results.push({ name, ok: true });
    console.log(`  ✓ ${name} (${Date.now() - started} ms)`);
    return true;
  } catch (err) {
    const file = path.join(SHOTS, `fail_${results.length + 1}.png`);
    await session.page.screenshot({ path: file, fullPage: true }).catch(() => {});
    results.push({ name, ok: false, error: err.message, screenshot: file });
    console.log(`  ✗ ${name}\n      ${err.message}\n      ảnh chụp: ${file}`);
    return false;
  }
}

/** Bấm khung giờ còn trống thứ `index` trên trang cụm sân (`times` lần liên tiếp); trả về nhãn "HH:MM - HH:MM". */
const clickFreeSlot = (page, index, times = 1) =>
  page.evaluate(async (i, count) => {
    const chips = [...document.querySelectorAll("button")].filter((b) => !b.disabled && /^\d{2}:\d{2} - \d{2}:\d{2}/.test(b.innerText.trim()));
    if (!chips[i]) throw new Error("Không đủ khung giờ trống để thử");
    for (let n = 0; n < count; n += 1) {
      chips[i].click();
      if (n < count - 1) await new Promise((resolve) => setTimeout(resolve, 40));
    }
    return chips[i].innerText.trim().slice(0, 13);
  }, index, times);

/** Chọn một ngày cách hôm nay `offset` ngày trên lịch của trang cụm sân. */
async function pickDate(page, offset) {
  const target = new Date();
  target.setDate(target.getDate() + offset);
  if (target.getMonth() !== new Date().getMonth()) await page.click('button[title="Tháng sau"]');
  await page.evaluate((day) => {
    const cells = [...document.querySelectorAll("div.grid.grid-cols-7 button")].filter((b) => !b.disabled && b.innerText.trim().split("\n")[0] === String(day));
    if (!cells[0]) throw new Error("Không thấy ô ngày trên lịch");
    cells[0].click();
  }, target.getDate());
}

async function main() {
  fs.mkdirSync(SHOTS, { recursive: true });
  browser = await puppeteer.launch({ headless: !process.argv.includes("--show"), args: ["--no-sandbox"] });
  let bookingCode = null;

  // ------------------------------------------------------------------ Khách chưa đăng nhập
  console.log("\nKhách chưa đăng nhập: chọn giờ rồi mới đăng nhập");
  const guest = await newSession("guest");
  await step(guest, "bấm chọn giờ khi chưa đăng nhập: đăng nhập xong quay lại đúng cụm sân đang xem", async (page) => {
    await page.goto(`${WEB}/venues/1`, { waitUntil: "networkidle2" });
    await waitForText(page, "2. Chọn Khung Giờ");
    await pickDate(page, 2);
    await sleep(800);
    await clickFreeSlot(page, 0);
    await page.waitForFunction(() => location.pathname === "/login", { timeout: TIMEOUT });
    await page.type('input[type="email"]', "player05@gmail.com");
    await page.type('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForFunction(() => location.pathname === "/venues/1", { timeout: TIMEOUT });
    await waitForText(page, "2. Chọn Khung Giờ");
  });
  await guest.context.close();

  // ------------------------------------------------------------------ Người chơi mới
  console.log("\nNgười chơi mới: đăng ký rồi thiết lập hồ sơ ghép trận");
  const newcomer = await newSession("newcomer");
  await step(newcomer, "đăng ký xong được dẫn tới thiết lập hồ sơ; bỏ qua được từng bước, xong thì sang Ghép Trận", async (page) => {
    const email = `e2e.moi.${Date.now()}@example.com`;
    await page.goto(`${WEB}/register`, { waitUntil: "networkidle2" });
    await page.type('input[type="text"]', "Người Chơi Mới");
    await page.type('input[type="email"]', email);
    const passwords = await page.$$('input[type="password"]');
    await passwords[0].type(PASSWORD);
    await passwords[1].type(PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForFunction(() => location.pathname === "/login" && location.search.includes("onboarding"), { timeout: TIMEOUT });
    await page.type('input[type="email"]', email);
    await page.type('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForFunction(() => location.pathname === "/onboarding", { timeout: TIMEOUT });
    await waitForText(page, "Bước 1/4");
    await clickText(page, "button", "3.0 - Đánh ổn định", { exact: true });
    await clickText(page, "button", "Tiếp tục", { exact: true });
    await waitForText(page, "Bước 2/4");
    await clickText(page, "button", "Để sau", { exact: true });
    await waitForText(page, "Bước 3/4");
    await clickText(page, "button", "Để sau", { exact: true });
    await waitForText(page, "Bước 4/4");
    await clickText(page, "button", "Toàn diện (All-Round)", { exact: true });
    await clickText(page, "button", "Giao lưu vui vẻ", { exact: true });
    await clickText(page, "button", "Hoàn tất", { exact: true });
    await page.waitForFunction(() => location.pathname === "/matches", { timeout: TIMEOUT });
    await waitForText(page, "Ghép Trận");
    // hồ sơ đã lưu đúng những gì vừa chọn; bước bỏ qua để trống, trang vẫn chạy và nhắc bổ sung
    const profile = await page.evaluate(async (api) => {
      const response = await fetch(`${api}/users/me`, { headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });
      return (await response.json()).player_profile;
    }, API);
    if (Number(profile.skill_level) !== 3 || profile.play_style !== "All-Round" || profile.purpose !== "recreational") {
      throw new Error(`Hồ sơ chưa lưu đúng sau khi thiết lập: ${JSON.stringify(profile)}`);
    }
    if (profile.date_of_birth) throw new Error("Bước ngày sinh đã bỏ qua nhưng hồ sơ vẫn có ngày sinh");
  });
  await newcomer.context.close();

  // ------------------------------------------------------------------ Người chơi 1
  console.log("\nNgười chơi 1: đặt sân, thanh toán cọc, mở phòng đấu");
  const p1 = await newSession("player01");
  await step(p1, "khách xem danh sách thường; người chơi đăng nhập thấy danh sách xếp sẵn theo gợi ý (Top 1…)", async (page) => {
    const topBadges = () => page.evaluate(() =>
      [...document.querySelectorAll("span")].map((s) => s.innerText.trim()).filter((t) => /^Top \d+$/.test(t)));
    await page.goto(`${WEB}/`, { waitUntil: "domcontentloaded" });
    await waitForText(page, "RUDAL Pickleball & Academy");
    if ((await topBadges()).length > 0) throw new Error("Khách chưa đăng nhập đã thấy nhãn gợi ý");

    await login(p1, WEB, "player01@gmail.com");
    await waitForText(page, "Danh Sách Cụm Sân");
    await waitForText(page, "RUDAL Pickleball & Academy");
    await waitForText(page, "Top 1");
    if (await hasText(page, "Gợi Ý Cho Bạn")) throw new Error("Trang chủ vẫn còn khối gợi ý cụm sân");
    if (await hasText(page, "Phù hợp nhất")) throw new Error("Trang chủ vẫn còn nút chọn cách xếp");
    const badges = await topBadges();
    const cards = await page.evaluate(() => [...document.querySelectorAll("button")].filter((b) => b.innerText.trim() === "Chi Tiết").length);
    if (cards === 0 || badges.length !== cards || badges[0] !== "Top 1") throw new Error(`Nhãn gợi ý sai: ${badges.join(", ")} trên ${cards} thẻ`);
  });

  await step(p1, "bấm đúp một khung giờ không bị tính hai lần; lịch khóa các ngày ngoài 60 ngày", async (page) => {
    await page.goto(`${WEB}/venues/1`, { waitUntil: "networkidle2" });
    await waitForText(page, "2. Chọn Khung Giờ");
    await pickDate(page, 2);
    await sleep(800);
    // khung trống thứ 8: không trùng khung dùng để đặt ở bước sau
    const label = await clickFreeSlot(page, 7, 2);
    await sleep(2000);
    const rowsInCart = () => page.evaluate((text) => [...document.querySelectorAll("div.sticky p")].filter((p) => p.innerText.includes(text)).length, label);
    const rows = await rowsInCart();
    if (rows > 1) throw new Error(`Bấm đúp làm khung ${label} xuất hiện ${rows} lần trong giỏ`);
    if (rows === 1) {
      // bỏ chọn để bước đặt sân bắt đầu với giỏ trống
      await clickText(page, "div.sticky button", "✕");
      await waitForText(page, "Chưa chọn khung giờ nào");
    }
    // 60 ngày luôn nằm trong ba tháng kế tiếp: sang tháng tối đa ba lần thì nút "Tháng sau" phải bị khóa
    const locked = await page.evaluate(async () => {
      const next = document.querySelector('button[title="Tháng sau"]');
      for (let i = 0; i < 3 && !next.disabled; i += 1) {
        next.click();
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
      return next.disabled && [...document.querySelectorAll("div.grid.grid-cols-7 button")].some((b) => b.disabled);
    });
    if (!locked) throw new Error("Lịch vẫn cho chọn ngày nằm ngoài 60 ngày");
  });

  const booked = await step(p1, "chọn khung giờ trống, tạo đơn và thanh toán cọc (giả lập)", async (page) => {
    await page.goto(`${WEB}/venues/1`, { waitUntil: "networkidle2" });
    await waitForText(page, "2. Chọn Khung Giờ");
    await pickDate(page, 2);
    await sleep(800);
    // khung thứ 6 còn trống của sân đầu tiên (tránh các khung dữ liệu mẫu đã dùng)
    await clickFreeSlot(page, 5);
    await waitForText(page, "Đã chọn:");
    await clickText(page, "button", "Đặt Sân & Thanh Toán Cọc 50%");
    await waitForText(page, "Số tiền cần chuyển");
    await clickText(page, "button", "Giả lập đã chuyển khoản");
    await waitForText(page, "Đã Xác Nhận Giữ Sân");
    await clickText(page, "button", "Xem Lịch Đặt Của Tôi");
    await page.waitForFunction(() => location.pathname === "/bookings", { timeout: TIMEOUT });
  });

  if (booked) {
    await step(p1, "đơn mới nằm ở mục Sắp diễn ra, có vé QR", async (page) => {
      await waitForText(page, "Đã xác nhận");
      bookingCode = await page.evaluate(() => (document.body.innerText.match(/PK2K\d{6}/) || [null])[0]);
      if (!bookingCode) throw new Error("Không đọc được mã đơn");
      await clickText(page, "button", "Chi tiết", { within: bookingCode, exact: true });
      await waitForText(page, "Vé nhận sân");
      const hasQr = await page.evaluate(() => !!document.querySelector("svg title") || !!document.querySelector("svg[role='img']"));
      if (!hasQr) throw new Error("Không thấy mã QR trên vé");
      console.log(`      mã đơn: ${bookingCode}`);
    });

    await step(p1, "mở phòng đấu trên đơn đã cọc", async (page) => {
      await clickText(page, "a", "Mở Phòng Đấu");
      await waitForText(page, "1. Chọn lịch sân");
      await clickText(page, 'button[type="submit"]', "Mở Phòng Đấu");
      await page.waitForFunction(() => location.pathname === "/matches", { timeout: TIMEOUT });
      await waitForText(page, "Chủ phòng");
    });

    // ---------------------------------------------------------------- Mô hình đề xuất phòng
    console.log("\nNgười chơi khác: mô hình đề xuất phòng đã tạo, rồi tham gia");
    const peer = await newSession("player06");
    await step(peer, "người cùng trình độ thấy phòng trong mục Phòng Đề Xuất của mô hình", async (page) => {
      await login(peer, WEB, "player06@gmail.com");
      await page.goto(`${WEB}/matches`, { waitUntil: "networkidle2" });
      await waitForText(page, "Phòng Đề Xuất");
      await waitForText(page, "Lê Hoàng Long");
      await waitForText(page, "Rất hợp với bạn");
      for (const jargon of ["Random Forest", "mô phỏng", "70%"]) {
        if (await hasText(page, jargon)) throw new Error(`Trang ghép trận còn chữ kỹ thuật: ${jargon}`);
      }
      // thẻ phòng gọn: mã đơn sân, ghi chú và danh sách thành viên chỉ hiện sau khi bấm Chi tiết
      if (await hasText(page, "Đã có sân (")) throw new Error("Thẻ phòng chưa thu gọn: vẫn hiện phần chi tiết");
      await clickText(page, "button", "Chi tiết", { within: "Lê Hoàng Long", exact: true });
      await waitForText(page, `Đã có sân (${bookingCode})`);
    });
    await peer.context.close();

    const far = await newSession("player10");
    await step(far, "người lệch xa trình độ không được đề xuất phòng đó, chỉ thấy ở Tất Cả Phòng Mở", async (page) => {
      await login(far, WEB, "player10@gmail.com");
      await page.goto(`${WEB}/matches`, { waitUntil: "networkidle2" });
      await waitForText(page, "Phòng Đề Xuất");
      await waitForText(page, "Tất Cả Phòng Mở (");
      await sleep(1000);
      if (await hasText(page, "Lê Hoàng Long")) throw new Error("Phòng lệch trình độ vẫn nằm trong mục đề xuất");
      await page.goto(`${WEB}/matches?tab=open`, { waitUntil: "networkidle2" });
      await waitForText(page, "Lê Hoàng Long");
      if (await roomIsRecommended(page, "Lê Hoàng Long")) throw new Error("Phòng lệch trình độ được gắn nhãn đề xuất");
    });
    await far.context.close();

    // ---------------------------------------------------------------- Người chơi 2
    console.log("\nNgười chơi 2: xin vào phòng, chủ phòng duyệt");
    const p2 = await newSession("player02");
    await step(p2, "thấy phòng của người chơi 1 kèm độ phù hợp, xin tham gia và chưa thấy số điện thoại", async (page) => {
      await login(p2, WEB, "player02@gmail.com");
      await page.goto(`${WEB}/matches?tab=open`, { waitUntil: "networkidle2" });
      await waitForText(page, "Lê Hoàng Long");
      const recommended = await roomIsRecommended(page, "Lê Hoàng Long");
      if (recommended === null) throw new Error("Không hiển thị độ phù hợp trên thẻ phòng");
      // mục Phòng Đề Xuất phải khớp với nhãn trên thẻ phòng
      await page.goto(`${WEB}/matches?tab=suggested`, { waitUntil: "networkidle2" });
      await waitForText(page, "Tất Cả Phòng Mở (");
      await sleep(1000);
      if ((await hasText(page, "Lê Hoàng Long")) !== recommended) throw new Error("Mục Phòng Đề Xuất không khớp với nhãn trên thẻ phòng");
      await page.goto(`${WEB}/matches?tab=open`, { waitUntil: "networkidle2" });
      await waitForText(page, "Lê Hoàng Long");
      await clickText(page, "button", "Xin Tham Gia", { within: "Lê Hoàng Long" });
      await waitForText(page, "Đã gửi yêu cầu tham gia");
      await waitForText(page, "Đang chờ duyệt");
      await clickText(page, "button", "Chi tiết", { within: "Lê Hoàng Long", exact: true });
      await waitForText(page, "0901***233"); // chờ duyệt: chỉ thấy số đã che
      if (await hasText(page, "0901112233")) throw new Error("Chưa được duyệt mà đã thấy đủ số điện thoại của chủ phòng");
    });
    await step(p1, "chủ phòng thấy yêu cầu và chấp nhận", async (page) => {
      await page.goto(`${WEB}/matches?tab=my_matches`, { waitUntil: "networkidle2" });
      // chuông báo có người xin vào phòng
      await page.waitForSelector('button[aria-label^="Thông báo, "]', { timeout: TIMEOUT });
      await page.click('button[aria-label^="Thông báo, "]');
      await waitForText(page, "Có người xin vào phòng của bạn");
      await page.keyboard.press("Escape");
      await page.goto(`${WEB}/matches?tab=my_matches`, { waitUntil: "networkidle2" });
      await waitForText(page, "1 yêu cầu chờ duyệt");
      await clickText(page, "button", "Chi tiết", { exact: true });
      await waitForText(page, "Yêu cầu tham gia");
      await clickText(page, "button", "Chấp Nhận", { exact: true });
      await waitForText(page, "vào phòng.");
    });
    await step(p2, "được duyệt thì thành viên thấy số điện thoại của nhau", async (page) => {
      await page.goto(`${WEB}/matches?tab=my_matches`, { waitUntil: "networkidle2" });
      await waitForText(page, "Lê Hoàng Long");
      await clickText(page, "button", "Chi tiết", { within: "Lê Hoàng Long", exact: true });
      await waitForText(page, "0901112233");
      if (await hasText(page, "Đang chờ duyệt")) throw new Error("Đã được duyệt nhưng thẻ phòng vẫn ghi đang chờ duyệt");
    });
    await p2.context.close();

    // ---------------------------------------------------------------- Người chơi 1 hủy
    console.log("\nNgười chơi 1: hủy đơn theo chính sách");
    await step(p1, "hủy đơn sớm: được hoàn 100%, phải nhập tài khoản nhận tiền", async (page) => {
      await page.goto(`${WEB}/bookings?tab=upcoming`, { waitUntil: "networkidle2" });
      await waitForText(page, bookingCode);
      await clickText(page, "button", "Hủy Đơn", { within: bookingCode, exact: true });
      await waitForText(page, "hoàn 100%");
      await fillByLabel(page, "Số tài khoản", "1900123456");
      await fillByLabel(page, "Tên chủ tài khoản", "LE HOANG LONG");
      await clickText(page, 'button[type="submit"]', "Xác Nhận Hủy Đơn");
      await waitForText(page, "Đã hủy đơn");
      await page.goto(`${WEB}/bookings?tab=cancelled`, { waitUntil: "networkidle2" });
      await waitForText(page, bookingCode);
      await waitForText(page, "Chờ hoàn");
      // bộ lọc của tab này: chỉ xem các đơn đang chờ hoàn tiền
      await page.select("#booking-refund-filter", "pending");
      await sleep(300);
      const waiting = await page.evaluate(() =>
        [...document.querySelectorAll("main div.rounded-2xl")]
          .filter((el) => el.querySelector("span.font-mono"))
          .map((el) => el.innerText.includes("Chờ hoàn")),
      );
      if (waiting.length === 0 || waiting.includes(false)) throw new Error("Lọc \"Chờ hoàn tiền\" vẫn hiện đơn không chờ hoàn");
      if (!(await hasText(page, bookingCode))) throw new Error("Đơn vừa hủy không có trong danh sách chờ hoàn tiền");
      await page.select("#booking-refund-filter", "all");
      await sleep(300);
      // các phiếu xếp theo ngày chơi: mới nhất trước, đổi được sang cũ nhất trước
      const cardDates = () =>
        page.evaluate(() =>
          [...document.querySelectorAll("main div.rounded-2xl")]
            .filter((el) => el.querySelector("span.font-mono"))
            .map((el) => {
              const found = el.innerText.match(/(\d{2})\/(\d{2})\/(\d{4})/);
              return found ? `${found[3]}-${found[2]}-${found[1]}` : "";
            }),
        );
      const newestFirst = await cardDates();
      if (newestFirst.join() !== [...newestFirst].sort().reverse().join()) {
        throw new Error(`Phiếu chưa xếp theo ngày chơi mới nhất trước: ${newestFirst.join(", ")}`);
      }
      if (newestFirst.length > 1) {
        await page.select("#booking-sort", "oldest");
        await sleep(300);
        const oldestFirst = await cardDates();
        if (oldestFirst.join() !== [...oldestFirst].sort().join()) {
          throw new Error(`Đổi sang cũ nhất trước nhưng thứ tự chưa đúng: ${oldestFirst.join(", ")}`);
        }
      }
      // phòng của đơn vừa hủy cũng bị hủy: mục Phòng Của Tôi chỉ giữ những phòng còn dùng được
      await page.goto(`${WEB}/matches?tab=my_matches`, { waitUntil: "networkidle2" });
      await waitForText(page, "Phòng Của Tôi (");
      await sleep(800);
      for (const closed of ["Đã hủy", "Đã kết thúc"]) {
        if (await hasText(page, closed)) throw new Error(`Mục Phòng Của Tôi vẫn hiện phòng "${closed}"`);
      }
    });
  }

  if (bookingCode) {
    const p2later = await newSession("player02-later");
    await step(p2later, "thành viên vào lại thì thấy thông báo phòng đấu đã bị hủy kèm lý do", async (page) => {
      await login(p2later, WEB, "player02@gmail.com");
      await page.waitForSelector('button[aria-label^="Thông báo"]', { timeout: TIMEOUT });
      await page.click('button[aria-label^="Thông báo"]');
      await waitForText(page, "Phòng đấu đã bị hủy");
      await waitForText(page, "chủ phòng đã hủy lịch đặt sân");
    });
    await p2later.context.close();
  }

  await step(p1, "hồ sơ chỉ còn các trường phục vụ ghép cặp và lưu được", async (page) => {
    await page.goto(`${WEB}/profile`, { waitUntil: "networkidle2" });
    await waitForText(page, "Mục đích chơi");
    await waitForText(page, "Khu vực thường chơi");
    if (await hasText(page, "giờ thường rảnh")) throw new Error("Hồ sơ vẫn còn lưới giờ rảnh");
    if (await hasText(page, "Tiện ích bạn ưu tiên")) throw new Error("Hồ sơ vẫn còn ô tiện ích ưa thích");
    if (await hasText(page, "Ngân sách tối đa")) throw new Error("Hồ sơ vẫn còn ô ngân sách");
    await clickText(page, 'button[type="submit"]', "Lưu Thông Tin");
    await waitForText(page, "Đã lưu hồ sơ");
    // lịch sử thanh toán: lọc theo loại giao dịch
    await page.goto(`${WEB}/profile?tab=payments`, { waitUntil: "networkidle2" });
    await waitForText(page, "Lịch Sử Thanh Toán");
    await page.waitForSelector("#txn-kind-filter", { timeout: TIMEOUT });
    const refundRows = () =>
      page.evaluate(() =>
        [...document.querySelectorAll("main div.rounded-2xl")]
          .filter((el) => el.querySelector("span.font-mono"))
          .map((el) => el.innerText.includes("Hoàn tiền")),
      );
    await page.select("#txn-kind-filter", "refund");
    await sleep(300);
    if ((await refundRows()).includes(false)) throw new Error("Lọc \"Hoàn tiền\" vẫn hiện giao dịch khác");
    await page.select("#txn-kind-filter", "paid");
    await sleep(300);
    const paidRows = await refundRows();
    if (paidRows.length === 0 || paidRows.includes(true)) throw new Error("Lọc \"Đã thanh toán\" hiện sai giao dịch");
  });
  await p1.context.close();

  // ------------------------------------------------------------------ Nhân viên
  console.log("\nNhân viên: bảng ca trực và xử lý tại quầy");
  const staff = await newSession("staff");
  await step(staff, "đăng nhập vào bảng ca trực của đúng cụm sân", async (page) => {
    await login(staff, WEB, "staff_rudal_1@pickleball.vn");
    await page.waitForFunction(() => location.pathname.startsWith("/staff"), { timeout: TIMEOUT });
    await waitForText(page, "RUDAL Pickleball & Academy");
    await waitForText(page, "Thu trong ngày");
    if (await hasText(page, "Đổi mật khẩu")) throw new Error("Cổng nhân viên không còn chức năng đổi mật khẩu");
  });
  if (bookingCode) {
    await step(staff, "tìm đơn theo mã và xác nhận đã hoàn tiền", async (page) => {
      await page.goto(`${WEB}/staff/bookings`, { waitUntil: "networkidle2" });
      await waitForText(page, "Quầy lễ tân");
      await page.type('input[aria-label="Mã đơn để check-in"]', bookingCode);
      await clickText(page, "button", "Tìm đơn");
      await waitForText(page, `Đơn ${bookingCode}`);
      // thiếu mã giao dịch ngân hàng thì không xác nhận được
      await clickText(page, "button", "Xác nhận đã chuyển hoàn");
      await waitForText(page, "Nhập mã giao dịch ngân hàng");
      await page.type('input[id^="refund-reference-"]', "FT26E2E000001");
      await clickText(page, "button", "Xác nhận đã chuyển hoàn");
      await waitForText(page, "Đã ghi nhận hoàn tiền");
      await waitForText(page, "FT26E2E000001");
      // đính kèm chứng từ (ảnh) sau khi xác nhận; tệp lưu riêng, chỉ xem được khi đã đăng nhập
      fs.mkdirSync(SHOTS, { recursive: true });
      const proof = path.join(SHOTS, "chung-tu-e2e.png");
      fs.writeFileSync(proof, Buffer.from(TINY_PNG, "base64"));
      const input = await page.$('label input[type="file"]');
      if (!input) throw new Error("Không thấy ô đính kèm chứng từ sau khi xác nhận hoàn tiền");
      await input.uploadFile(proof);
      await waitForText(page, "Đã lưu chứng từ hoàn tiền");
      await waitForText(page, "Xem chứng từ");
    });
  }
  await step(staff, "tạo đơn tại quầy từ một ô trống trên lịch", async (page) => {
    await page.goto(`${WEB}/staff/bookings`, { waitUntil: "networkidle2" });
    await waitForText(page, "Quầy lễ tân");
    await page.click('button[aria-label="Ngày sau"]');
    await sleep(1000);
    await page.evaluate(() => {
      const free = [...document.querySelectorAll("table button")].filter((b) => !b.disabled && b.innerText.trim() === "+");
      if (free.length < 3) throw new Error("Không có ô trống trên lịch");
      free[2].click();
    });
    await waitForText(page, "Tạo đơn tại quầy");
    await fillByLabel(page, "Tên khách", "Khách kiểm thử");
    await clickText(page, 'button[type="submit"]', "Tạo đơn", { exact: true });
    await waitForText(page, "Đã tạo đơn tại quầy");
    await waitForText(page, "Khách kiểm thử");
  });
  await step(staff, "kết ca: nhập tiền vốn và tiền mặt đếm được, xem đối chiếu rồi xác nhận", async (page) => {
    await page.goto(`${WEB}/staff/dashboard`, { waitUntil: "networkidle2" });
    await waitForText(page, "Thu trong ngày");
    await clickText(page, "button", "Kết ca", { exact: true });
    await waitForText(page, "Kết ca trong ngày");
    await page.waitForSelector("#shift-opening-float", { timeout: TIMEOUT });
    // số âm bị từ chối ngay, chưa có gì được lưu
    await page.type("#shift-opening-float", "-5");
    await page.type("#shift-counted-cash", "200000");
    await clickText(page, 'button[type="submit"]', "Đối chiếu", { exact: true });
    await waitForText(page, "Số tiền phải là số nguyên, không âm");
    await page.click("#shift-opening-float", { clickCount: 3 });
    await page.type("#shift-opening-float", "200000");
    await clickText(page, 'button[type="submit"]', "Đối chiếu", { exact: true });
    await waitForText(page, "Tiền mặt phải có trong két");
    await clickText(page, "button", "Xác nhận kết ca", { exact: true });
    await waitForText(page, "Số liệu đã được lưu");
  });
  await step(staff, "nhân viên không vào được cổng chủ sân", async (page) => {
    await page.goto(`${WEB}/owner/venues`, { waitUntil: "networkidle2" });
    await page.waitForFunction(() => location.pathname.startsWith("/staff"), { timeout: TIMEOUT });
  });
  await staff.context.close();

  // ------------------------------------------------------------------ Chủ sân
  console.log("\nChủ sân: tổng quan và cài đặt cụm sân");
  const owner = await newSession("owner");
  await step(owner, "bảng tổng quan hiển thị thực thu từ sổ giao dịch", async (page) => {
    await login(owner, WEB, "owner_rudal@pickleball.vn");
    await page.waitForFunction(() => location.pathname.startsWith("/owner"), { timeout: TIMEOUT });
    await waitForText(page, "Thu hôm nay");
    await waitForText(page, "Tổng thực thu");
    await waitForText(page, "Lịch hôm nay");
    await waitForText(page, "Giao dịch gần đây");
  });
  await step(owner, "lưu bảng giá và giờ hoạt động", async (page) => {
    await page.goto(`${WEB}/owner/venues?tab=courts_pricing`, { waitUntil: "networkidle2" });
    await waitForText(page, "Bảng giá mỗi giờ");
    await clickText(page, 'button[type="submit"]', "Lưu bảng giá");
    await waitForText(page, "Đã lưu bảng giá");
    await page.goto(`${WEB}/owner/venues?tab=hours`, { waitUntil: "networkidle2" });
    await waitForText(page, "Giờ hoạt động trong tuần");
    await clickText(page, 'button[type="submit"]', "Lưu giờ hoạt động");
    await waitForText(page, "Đã lưu giờ hoạt động");
  });
  await step(owner, "trang cài đặt không còn nút đăng nhập nhanh hay số tài khoản mặc định", async (page) => {
    await page.goto(`${WEB}/owner/venues`, { waitUntil: "networkidle2" });
    await waitForText(page, "Tài khoản nhận tiền cọc");
    const text = await page.evaluate(() => document.body.innerText);
    for (const forbidden of ["Đăng nhập Sân", "password123", "0765883535"]) {
      if (text.includes(forbidden)) throw new Error(`Trang vẫn chứa "${forbidden}"`);
    }
  });
  await owner.context.close();

  // ------------------------------------------------------------------ Người chơi không vào được cổng quản lý
  const outsider = await newSession("player03");
  await step(outsider, "người chơi bị chuyển khỏi cổng chủ sân và cổng nhân viên", async (page) => {
    await login(outsider, WEB, "player03@gmail.com");
    for (const url of ["/owner/dashboard", "/staff/bookings"]) {
      await page.goto(`${WEB}${url}`, { waitUntil: "networkidle2" });
      await page.waitForFunction(() => location.pathname === "/", { timeout: TIMEOUT });
    }
  });
  await outsider.context.close();

  // ------------------------------------------------------------------ Quản trị viên
  console.log("\nQuản trị viên: cổng quản trị");
  const admin = await newSession("admin");
  await step(admin, "tổng quan chỉ có số liệu vận hành, không hiển thị chi tiết kỹ thuật của mô hình", async (page) => {
    await login(admin, ADMIN, "admin@example.com");
    await waitForText(page, "Thực thu toàn hệ thống");
    await waitForText(page, "Thống kê doanh thu và đơn đặt sân");
    if (await hasText(page, "Phân bố trạng thái")) throw new Error("Trang tổng quan vẫn còn khối phân bố trạng thái");
    for (const jargon of ["Random Forest", "Độ chính xác", "phiếu ghép cặp"]) {
      if (await hasText(page, jargon)) throw new Error(`Trang tổng quan còn nội dung kỹ thuật: ${jargon}`);
    }
    // thống kê doanh thu và đơn đặt sân: đổi được giữa từng ngày, từng tháng và từng năm
    await waitForText(page, "Thống kê doanh thu và đơn đặt sân");
    await page.waitForSelector('select[aria-label="Tháng thống kê"]', { timeout: TIMEOUT });
    await clickText(page, "button", "Theo tháng", { exact: true });
    await waitForText(page, "Th12");
    await clickText(page, "button", "Theo năm", { exact: true });
    await page.waitForFunction(() => !document.querySelector('select[aria-label="Năm thống kê"]'), { timeout: TIMEOUT });
    // bên dưới biểu đồ: cụm sân nào bán được bao nhiêu trong cùng khoảng thời gian
    await waitForText(page, "Theo cụm sân");
    await waitForText(page, "D-Joy Pickleball Thủ Thiêm");
  });
  await step(admin, "khóa rồi mở khóa một tài khoản", async (page) => {
    await clickText(page, "nav button", "Tài khoản");
    await waitForText(page, "player18@gmail.com");
    await clickText(page, "button", "Chi tiết", { within: "player18@gmail.com", exact: true });
    await waitForText(page, "Chi tiết tài khoản");
    await waitForText(page, "Mục đích chơi");
    await clickText(page, "button", "Đóng", { exact: true });
    await clickText(page, "button", "Khóa", { within: "player18@gmail.com", exact: true });
    await waitForText(page, "Đã khóa tài khoản");
    await clickText(page, "button", "Mở khóa", { within: "player18@gmail.com", exact: true });
    await waitForText(page, "Đã mở khóa tài khoản");
  });
  await step(admin, "các tab cụm sân, đơn đặt, sổ giao dịch, phòng đấu đều có dữ liệu", async (page) => {
    await clickText(page, "nav button", "Cụm sân");
    await waitForText(page, "D-Joy Pickleball Thủ Thiêm");
    await clickText(page, "nav button", "Đơn đặt sân");
    await waitForText(page, "PK2K000001");
    await clickText(page, "nav button", "Sổ giao dịch");
    await waitForText(page, "TX000001");
    await clickText(page, "nav button", "Phòng đấu");
    await waitForText(page, "Đang tuyển");
  });
  await admin.context.close();

  await browser.close();

  // ------------------------------------------------------------------ Tổng kết
  const failed = results.filter((r) => !r.ok);
  console.log(`\nKết quả: ${results.length - failed.length}/${results.length} bước đạt.`);
  if (problems.length > 0) {
    console.log(`Lỗi ghi nhận trong lúc chạy (${problems.length}):`);
    [...new Set(problems)].forEach((p) => console.log("  - " + p));
  }
  process.exit(failed.length > 0 || problems.length > 0 ? 1 : 0);
}

main().catch(async (err) => {
  console.error("Script dừng do lỗi:", err);
  if (browser) await browser.close().catch(() => {});
  process.exit(1);
});
