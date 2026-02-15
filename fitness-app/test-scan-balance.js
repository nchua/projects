#!/usr/bin/env node

/**
 * Test scan balance endpoints (screenshot scanner paywall)
 */

const http = require('http');
const https = require('https');

const BASE_URL = process.env.API_BASE_URL || 'https://backend-production-e316.up.railway.app';

let authToken = null;

function makeRequest(method, path, data = null, token = null) {
    return new Promise((resolve, reject) => {
        const url = new URL(path, BASE_URL);
        const isHttps = url.protocol === 'https:';
        const options = {
            hostname: url.hostname,
            port: url.port || (isHttps ? 443 : 80),
            path: url.pathname + url.search,
            method: method,
            headers: {
                'Content-Type': 'application/json',
            }
        };

        if (token) {
            options.headers['Authorization'] = `Bearer ${token}`;
        }

        const lib = isHttps ? https : http;
        const req = lib.request(options, (res) => {
            let body = '';
            res.on('data', (chunk) => body += chunk);
            res.on('end', () => {
                try {
                    const response = JSON.parse(body);
                    resolve({ status: res.statusCode, data: response });
                } catch (e) {
                    resolve({ status: res.statusCode, data: body });
                }
            });
        });

        req.on('error', reject);

        if (data) {
            req.write(JSON.stringify(data));
        }
        req.end();
    });
}

async function login() {
    const email = process.env.SEED_USER_EMAIL || 'test@example.com';
    const password = process.env.SEED_USER_PASSWORD || 'TestPass123!';

    console.log(`\n🔐 Logging in as ${email}...`);
    const res = await makeRequest('POST', '/auth/login', { email, password });

    if (res.status === 200) {
        authToken = res.data.access_token;
        console.log('✅ Login successful');
        return true;
    } else {
        console.log(`❌ Login failed: ${JSON.stringify(res.data)}`);
        return false;
    }
}

async function testGetScanBalance() {
    console.log('\n📊 GET /scan-balance');
    const res = await makeRequest('GET', '/scan-balance', null, authToken);
    console.log(`   Status: ${res.status}`);
    console.log(`   Data: ${JSON.stringify(res.data, null, 2)}`);

    if (res.status === 200) {
        console.log('✅ Get scan balance: PASS');
        return res.data;
    } else {
        console.log('❌ Get scan balance: FAIL');
        return null;
    }
}

async function testVerifyPurchase(transactionId, productId) {
    console.log(`\n💳 POST /scan-balance/verify-purchase (${productId})`);
    const res = await makeRequest('POST', '/scan-balance/verify-purchase', {
        transaction_id: transactionId,
        product_id: productId,
        signed_transaction: null
    }, authToken);
    console.log(`   Status: ${res.status}`);
    console.log(`   Data: ${JSON.stringify(res.data, null, 2)}`);

    if (res.status === 200 && res.data.success) {
        console.log('✅ Verify purchase: PASS');
    } else {
        console.log('❌ Verify purchase: FAIL');
    }
    return res;
}

async function testDuplicateTransaction(transactionId, productId) {
    console.log(`\n🔄 POST /scan-balance/verify-purchase (duplicate: ${transactionId})`);
    const res = await makeRequest('POST', '/scan-balance/verify-purchase', {
        transaction_id: transactionId,
        product_id: productId,
        signed_transaction: null
    }, authToken);
    console.log(`   Status: ${res.status}`);
    console.log(`   Credits added: ${res.data.credits_added}`);

    if (res.status === 200 && res.data.credits_added === 0) {
        console.log('✅ Duplicate prevention: PASS (0 credits added)');
    } else {
        console.log('❌ Duplicate prevention: FAIL');
    }
}

async function testRestorePurchases() {
    console.log('\n🔄 POST /scan-balance/restore-purchases');
    const res = await makeRequest('POST', '/scan-balance/restore-purchases', {}, authToken);
    console.log(`   Status: ${res.status}`);
    console.log(`   Data: ${JSON.stringify(res.data, null, 2)}`);

    if (res.status === 200) {
        console.log('✅ Restore purchases: PASS');
    } else {
        console.log('❌ Restore purchases: FAIL');
    }
}

async function testInvalidProduct() {
    console.log('\n🚫 POST /scan-balance/verify-purchase (invalid product)');
    const res = await makeRequest('POST', '/scan-balance/verify-purchase', {
        transaction_id: 'test-invalid-product',
        product_id: 'com.invalid.product',
        signed_transaction: null
    }, authToken);
    console.log(`   Status: ${res.status}`);

    if (res.status === 400) {
        console.log('✅ Invalid product rejected: PASS');
    } else {
        console.log('❌ Invalid product rejected: FAIL');
    }
}

async function main() {
    console.log('=== Scan Balance API Tests ===');
    console.log(`Base URL: ${BASE_URL}`);

    const loggedIn = await login();
    if (!loggedIn) {
        console.log('\n⚠️  Cannot test without authentication. Set SEED_USER_EMAIL and SEED_USER_PASSWORD.');
        process.exit(1);
    }

    // 1. Get initial balance (should create with 3 free credits)
    await testGetScanBalance();

    // 2. Verify a purchase (Quick Pack - 20 scans)
    const txId = `test-tx-${Date.now()}`;
    await testVerifyPurchase(txId, 'com.nickchua.fitnessapp.scan_20');

    // 3. Check balance updated
    await testGetScanBalance();

    // 4. Test duplicate transaction prevention
    await testDuplicateTransaction(txId, 'com.nickchua.fitnessapp.scan_20');

    // 5. Test invalid product
    await testInvalidProduct();

    // 6. Test restore purchases
    await testRestorePurchases();

    // 7. Final balance check
    await testGetScanBalance();

    console.log('\n=== Tests Complete ===\n');
}

main().catch(console.error);
