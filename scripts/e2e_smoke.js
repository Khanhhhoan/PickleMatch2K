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
const SHOTS = path.join(__dirname, "../test-results/screenshots");
const TIMEOUT = 15000;

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

  // ------------------------------------------------------------------ Người chơi 1
  console.log("\nNgười chơi 1: đặt sân, thanh toán cọc, mở phòng đấu");
  const p1 = await newSession("player01");
  await step(p1, "đăng nhập và xem trang chủ có danh sách + gợi ý cụm sân", async (page) => {
    await login(p1, WEB, "player01@gmail.com");
    await waitForText(page, "Danh Sách Cụm Sân");
    await waitForText(page, "Gợi Ý Cho Bạn Hôm Nay");
    await waitForText(page, "RUDAL Pickleball & Academy");
  });

  const booked = await step(p1, "chọn khung giờ trống, tạo đơn và thanh toán cọc (giả lập)", async (page) => {
    await page.goto(`${WEB}/venues/1`, { waitUntil: "networkidle2" });
    await waitForText(page, "2. Chọn Khung Giờ");
    await pickDate(page, 2);
    await sleep(800);
    // khung thứ 6 còn trống của sân đầu tiên (tránh các khung dữ liệu mẫu đã dùng)
    await page.evaluate(() => {
      const chips = [...document.querySelectorAll("button")].filter((b) => !b.disabled && /^\d{2}:\d{2} - \d{2}:\d{2}/.test(b.innerText.trim()));
      if (chips.length < 6) throw new Error("Không đủ khung giờ trống để thử");
      chips[5].click();
    });
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

    // ---------------------------------------------------------------- Người chơi 2
    console.log("\nNgười chơi 2: xem độ phù hợp và tham gia phòng");
    const p2 = await newSession("player02");
    await step(p2, "thấy phòng của người chơi 1 kèm độ phù hợp và tham gia", async (page) => {
      await login(p2, WEB, "player02@gmail.com");
      await page.goto(`${WEB}/matches?tab=open`, { waitUntil: "networkidle2" });
      await waitForText(page, "Lê Hoàng Long");
      if (!(await hasText(page, "Phù hợp"))) throw new Error("Không hiển thị độ phù hợp từ mô hình");
      await clickText(page, "button", "Tham Gia Phòng", { within: "Lê Hoàng Long" });
      await waitForText(page, "Đã tham gia phòng");
      await waitForText(page, "0901112233"); // thành viên cùng phòng thấy số điện thoại của nhau
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
    });
  }

  await step(p1, "hồ sơ có các trường phục vụ gợi ý và lưu được", async (page) => {
    await page.goto(`${WEB}/profile`, { waitUntil: "networkidle2" });
    await waitForText(page, "Khung giờ thường rảnh trong tuần");
    await waitForText(page, "Tiện ích bạn ưu tiên khi chọn sân");
    await clickText(page, 'button[type="submit"]', "Lưu Thông Tin");
    await waitForText(page, "Đã lưu hồ sơ");
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
  });
  if (bookingCode) {
    await step(staff, "tìm đơn theo mã và xác nhận đã hoàn tiền", async (page) => {
      await page.goto(`${WEB}/staff/bookings`, { waitUntil: "networkidle2" });
      await waitForText(page, "Quầy lễ tân");
      await page.type('input[aria-label="Mã đơn để check-in"]', bookingCode);
      await clickText(page, "button", "Tìm đơn");
      await waitForText(page, `Đơn ${bookingCode}`);
      await clickText(page, "button", "Xác nhận đã chuyển hoàn");
      await waitForText(page, "Đã ghi nhận hoàn tiền");
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
    await waitForText(page, "Thực thu (đã trừ hoàn tiền)");
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
  await step(admin, "tổng quan có số liệu và thông tin trung thực về mô hình", async (page) => {
    await login(admin, ADMIN, "admin@example.com");
    await waitForText(page, "Thực thu toàn hệ thống");
    await waitForText(page, "Mô hình ghép cặp người chơi");
    await waitForText(page, "Random Forest (đang dùng)");
  });
  await step(admin, "khóa rồi mở khóa một tài khoản", async (page) => {
    await clickText(page, "nav button", "Tài khoản");
    await waitForText(page, "player18@gmail.com");
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
