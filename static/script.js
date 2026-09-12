document.addEventListener("DOMContentLoaded", function() {
    const input = document.getElementById("stockSearchInput");
    const dropdown = document.getElementById("searchDropdown");

    if (!input) return;

    input.addEventListener("input", async function() {
        const query = this.value.trim();
        if (query.length === 0) {
            dropdown.style.display = "none";
            return;
        }

        try {
            // เรียกใช้งาน API ที่เราสร้างขึ้น
            const response = await fetch(`/api/search_stocks?q=${encodeURIComponent(query)}`);
            const stocks = await response.json();

            dropdown.innerHTML = "";
            if (stocks.length > 0) {
                stocks.forEach(stock => {
                    const li = document.createElement("listyle");
                    li.style.padding = "10px";
                    li.style.cursor = "pointer";
                    li.style.borderBottom = "1px solid #334155";
                    li.innerHTML = `<strong>${stock.symbol}</strong> - <span style="color: #94a3b8;">${stock.name}</span>`;
                    
                    // เมื่อคลิกเลือกหุ้นจาก Dropdown
                    li.addEventListener("click", function() {
                        input.value = stock.symbol;
                        dropdown.style.display = "none";
                    });

                    // เอฟเฟกต์เมาส์ชี้
                    li.addEventListener("mouseenter", () => li.style.background = "#334155");
                    li.addEventListener("mouseleave", () => li.style.background = "transparent");

                    dropdown.appendChild(li);
                });
                dropdown.style.display = "block";
            } else {
                dropdown.style.display = "none";
            }
        } catch (error) {
            console.error("Error searching stocks:", error);
        }
    });

    // ซ่อน Dropdown เมื่อคลิกพื้นที่อื่นบนหน้าจอ
    document.addEventListener("click", function(e) {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = "none";
        }
    });
});