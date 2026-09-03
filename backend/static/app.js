let currentTheme = 'system';
        let typologyChartInstance = null;
        let tierChartInstance = null;
        let featureChartInstance = null;
        let visNetworkInstance = null;
        let autoStreamInterval = null;
        let lastSQLResultData = null;

        function initTheme() {
            const saved = localStorage.getItem('aml_theme') || 'system';
            setTheme(saved);
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
                if (currentTheme === 'system') applyTheme('system');
            });
        }

        function setTheme(theme) {
            currentTheme = theme;
            localStorage.setItem('aml_theme', theme);
            ['system', 'dark', 'light'].forEach(t => {
                const btn = document.getElementById('theme-' + t);
                if (btn) {
                    if (t === theme) {
                        btn.classList.add('bg-cyan-500', 'text-white');
                        btn.classList.remove('text-muted');
                    } else {
                        btn.classList.remove('bg-cyan-500', 'text-white');
                        btn.classList.add('text-muted');
                    }
                }
            });
            applyTheme(theme);
        }

        function applyTheme(theme) {
            const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
            if (isDark) {
                document.documentElement.classList.add('dark');
            } else {
                document.documentElement.classList.remove('dark');
            }
            if (typologyChartInstance) refreshData();
        }

        document.addEventListener('DOMContentLoaded', () => {
            initTheme();
            if (typeof lucide !== 'undefined' && lucide.createIcons) { try { lucide.createIcons(); } catch(e){} }
            refreshData();
            loadModelMetrics();
            searchTransactions();
            loadSQLSchema();
        });

        function switchTab(tabId) {
            ['dashboard', 'sql', 'alerts', 'network', 'entity', 'transactions', 'tester', 'model'].forEach(t => {
                const el = document.getElementById('tab-' + t);
                const nav = document.getElementById('nav-' + t);
                if (el) el.classList.add('hidden');
                if (nav) {
                    nav.classList.remove('bg-cyan-500/10', 'text-cyan-500', 'border', 'border-cyan-500/20');
                    nav.classList.add('text-muted');
                }
            });

            const activeEl = document.getElementById('tab-' + tabId);
            const activeNav = document.getElementById('nav-' + tabId);
            if (activeEl) activeEl.classList.remove('hidden');
            if (activeNav) {
                activeNav.classList.add('bg-cyan-500/10', 'text-cyan-500', 'border', 'border-cyan-500/20');
                activeNav.classList.remove('text-muted');
            }

            if (tabId === 'alerts') loadAlerts();
            if (tabId === 'network') renderNetworkForAccount();
            if (tabId === 'entity') loadAccountProfile();
            if (tabId === 'transactions') searchTransactions();
            if (tabId === 'sql') loadSQLSchema();
            if (typeof lucide !== 'undefined' && lucide.createIcons) { try { lucide.createIcons(); } catch(e){} }
        }

        async function refreshData() {
            try {
                const res = await fetch('/api/stats');
                const stats = await res.json();

                document.getElementById('stat-total-tx').innerText = Number(stats.total_transactions).toLocaleString();
                document.getElementById('stat-total-vol').innerText = '$' + Number(stats.total_volume).toLocaleString('en-US', { minimumFractionDigits: 2 });
                document.getElementById('stat-flagged-tx').innerText = Number(stats.flagged_transactions).toLocaleString();
                document.getElementById('stat-flagged-vol').innerText = '$' + Number(stats.flagged_volume).toLocaleString('en-US', { minimumFractionDigits: 2 }) + ' intercepted';
                
                const totalAlerts = Object.values(stats.alerts_by_status || {}).reduce((a, b) => a + b, 0);
                document.getElementById('badge-alert-count').innerText = totalAlerts.toLocaleString();

                renderCharts(stats);
                loadRecentAlerts();
            } catch (err) {
                console.error('Error loading stats:', err);
            }
        }

        function renderCharts(stats) {
            const isDark = document.documentElement.classList.contains('dark');
            const textColor = isDark ? '#9ca3af' : '#475569';
            const gridColor = isDark ? '#1f2937' : '#cbd5e1';

            const ctxTyp = document.getElementById('typologyChart').getContext('2d');
            const typData = stats.laundering_breakdown || [];
            
            if (typologyChartInstance) typologyChartInstance.destroy();
            typologyChartInstance = new Chart(ctxTyp, {
                type: 'bar',
                data: {
                    labels: typData.map(d => d.type.replace(/_/g, ' ')),
                    datasets: [{
                        label: 'Interceptions Count',
                        data: typData.map(d => d.count),
                        backgroundColor: '#06b6d4',
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false }, ticks: { color: textColor, font: { size: 10 } } },
                        y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 } } }
                    }
                }
            });

            const ctxTier = document.getElementById('tierChart').getContext('2d');
            const tiers = stats.tier_distribution || {};
            
            if (tierChartInstance) tierChartInstance.destroy();
            tierChartInstance = new Chart(ctxTier, {
                type: 'doughnut',
                data: {
                    labels: Object.keys(tiers),
                    datasets: [{
                        data: Object.values(tiers),
                        backgroundColor: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'bottom', labels: { color: textColor, font: { size: 10 } } } },
                    cutout: '70%'
                }
            });
        }

        async function loadRecentAlerts() {
            try {
                const res = await fetch('/api/alerts?limit=6');
                const data = await res.json();
                const tbody = document.getElementById('recentAlertsTable');
                tbody.innerHTML = '';

                (data.alerts || []).forEach(a => {
                    const row = document.createElement('tr');
                    row.className = 'hover:bg-cyan-500/5 transition-colors';
                    const sevColor = a.severity === 'CRITICAL' ? 'text-rose-500 bg-rose-500/10 border-rose-500/20' : (a.severity === 'HIGH' ? 'text-amber-500 bg-amber-500/10 border-amber-500/20' : 'text-blue-500 bg-blue-500/10 border-blue-500/20');
                    
                    row.innerHTML = `
                        <td class="p-3 font-semibold">${a.alert_id}</td>
                        <td class="p-3 text-cyan-500 font-semibold">${a.alert_type}</td>
                        <td class="p-3 text-emerald-500 font-bold">$${Number(a.amount).toLocaleString()}</td>
                        <td class="p-3 text-muted">${a.sender_account.slice(-4)} &rarr; ${a.receiver_account.slice(-4)}</td>
                        <td class="p-3"><span class="px-2 py-0.5 rounded-full border text-[10px] font-bold ${sevColor}">${a.risk_score}/100</span></td>
                        <td class="p-3">${a.status}</td>
                        <td class="p-3 text-right">
                            <button onclick="openSarModal('${a.alert_id}', '${a.sender_account}', '${a.receiver_account}', ${a.amount}, '${a.alert_type}', ${a.risk_score})" class="px-2.5 py-1 rounded-lg bg-cyan-500/10 hover:bg-cyan-500 text-cyan-500 hover:text-white border border-cyan-500/20 text-[11px] transition-colors">
                                File SAR
                            </button>
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            } catch (err) {
                console.error(err);
            }
        }

        async function loadAlerts() {
            const sev = document.getElementById('filterSeverity').value;
            const stat = document.getElementById('filterStatus').value;
            const res = await fetch(`/api/alerts?severity=${sev}&status=${stat}&limit=50`);
            const data = await res.json();
            const tbody = document.getElementById('fullAlertsTable');
            tbody.innerHTML = '';

            (data.alerts || []).forEach(a => {
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-cyan-500/5 transition-colors';
                const sevColor = a.severity === 'CRITICAL' ? 'text-rose-500 bg-rose-500/10 border-rose-500/20' : (a.severity === 'HIGH' ? 'text-amber-500 bg-amber-500/10 border-amber-500/20' : 'text-blue-500 bg-blue-500/10 border-blue-500/20');
                
                tr.innerHTML = `
                    <td class="p-3 font-semibold">${a.alert_id}</td>
                    <td class="p-3"><span class="px-2 py-0.5 rounded-full border text-[10px] font-bold ${sevColor}">${a.severity}</span></td>
                    <td class="p-3 text-emerald-500 font-bold">$${Number(a.amount).toLocaleString()}</td>
                    <td class="p-3">${a.sender_account} &rarr; ${a.receiver_account}</td>
                    <td class="p-3">
                        <span class="text-cyan-500 font-bold">${a.risk_score}</span>
                        <p class="text-[10px] text-muted truncate max-w-xs">${a.rule_reason || ''}</p>
                    </td>
                    <td class="p-3"><span class="px-2 py-0.5 rounded bg-subtle text-[10px]">${a.status}</span></td>
                    <td class="p-3 text-muted">${a.assigned_to}</td>
                    <td class="p-3 text-right space-x-1.5">
                        <button onclick="triageStatus('${a.alert_id}', 'UNDER_INVESTIGATION')" class="px-2 py-1 rounded bg-subtle hover:opacity-80 text-[11px] border border-theme">Investigate</button>
                        <button onclick="openSarModal('${a.alert_id}', '${a.sender_account}', '${a.receiver_account}', ${a.amount}, '${a.alert_type}', ${a.risk_score})" class="px-2 py-1 rounded bg-rose-500/10 hover:bg-rose-500 text-rose-500 hover:text-white border border-rose-500/20 text-[11px]">SAR</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        async function triageStatus(alertId, newStatus) {
            await fetch(`/api/alerts/${alertId}/triage`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus, assigned_to: 'AML Compliance Officer', investigator_notes: 'Under active review.' })
            });
            loadAlerts();
            refreshData();
        }

        async function simulateStream(batchSize) {
            const btn = document.getElementById('streamBtn');
            btn.innerHTML = '<span>Streaming...</span>';
            btn.classList.add('opacity-75');

            try {
                const res = await fetch(`/api/simulate-stream?batch_size=${batchSize}`, { method: 'POST' });
                await refreshData();
                loadAlerts();
                searchTransactions();
            } finally {
                btn.innerHTML = '<i data-lucide="zap" class="w-4 h-4"></i><span>Inject Stream (15 TX)</span>';
                btn.classList.remove('opacity-75');
                if (typeof lucide !== 'undefined' && lucide.createIcons) { try { lucide.createIcons(); } catch(e){} }
            }
        }

        function toggleAutoStream() {
            const toggle = document.getElementById('autoStreamToggle');
            const dot = document.getElementById('toggleDot');
            
            if (autoStreamInterval) {
                clearInterval(autoStreamInterval);
                autoStreamInterval = null;
                toggle.classList.remove('bg-cyan-600');
                toggle.classList.add('bg-gray-600');
                dot.style.transform = 'translateX(0px)';
            } else {
                autoStreamInterval = setInterval(() => {
                    simulateStream(6);
                }, 4000);
                toggle.classList.remove('bg-gray-600');
                toggle.classList.add('bg-cyan-600');
                dot.style.transform = 'translateX(16px)';
            }
        }

        async function renderNetworkForAccount() {
            let acc = document.getElementById('targetAccountInput').value.trim() || '8724731955';

            try {
                const res = await fetch(`/api/network-graph/${acc}`);
                const data = await res.json();
                
                const container = document.getElementById('visNetworkContainer');
                const isDark = document.documentElement.classList.contains('dark');
                const labelColor = isDark ? '#f3f4f6' : '#1e293b';

                const graphData = {
                    nodes: new vis.DataSet(data.nodes.map(n => ({ ...n, font: { color: labelColor, size: 12, face: 'JetBrains Mono' } }))),
                    edges: new vis.DataSet(data.edges)
                };
                
                const options = {
                    nodes: { shape: 'dot', size: 20, borderWidth: 2 },
                    edges: { width: 2, font: { color: '#9ca3af', size: 10, align: 'middle' }, smooth: { type: 'continuous' } },
                    physics: { stabilization: true, barnesHut: { gravitationalConstant: -3000, springLength: 120 } }
                };

                visNetworkInstance = new vis.Network(container, graphData, options);
            } catch (err) {
                console.error(err);
            }
        }

        async function loadAccountProfile() {
            const acc = document.getElementById('dossierAccountInput').value.trim() || '8724731955';
            try {
                const res = await fetch(`/api/account/${acc}/profile`);
                const data = await res.json();

                document.getElementById('dosRisk').innerText = data.risk_rating + '/100';
                document.getElementById('dosTier').innerText = data.risk_tier;
                document.getElementById('dosInflow').innerText = '$' + Number(data.total_inflow).toLocaleString();
                document.getElementById('dosOutflow').innerText = '$' + Number(data.total_outflow).toLocaleString();
                document.getElementById('dosAlertsCount').innerText = data.flagged_alerts_count;

                const tbody = document.getElementById('dosTxTable');
                tbody.innerHTML = '';
                (data.recent_transactions || []).forEach(t => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td class="p-2.5 text-cyan-500 font-semibold">${t.tx_id}</td>
                        <td class="p-2.5 text-muted">${t.date} ${t.time}</td>
                        <td class="p-2.5">${t.sender_account.slice(-4)} &rarr; ${t.receiver_account.slice(-4)}</td>
                        <td class="p-2.5 text-emerald-500 font-bold">$${Number(t.amount).toLocaleString()}</td>
                        <td class="p-2.5">${t.payment_type}</td>
                        <td class="p-2.5 text-rose-500 font-bold">${t.risk_score}</td>
                    `;
                    tbody.appendChild(row);
                });
            } catch (err) {
                console.error(err);
            }
        }

        async function searchTransactions() {
            const query = document.getElementById('txSearchInput')?.value.trim() || '';
            const tier = document.getElementById('txTierFilter')?.value || 'ALL';
            
            try {
                const res = await fetch(`/api/transactions?search=${query}&risk_tier=${tier}&limit=30`);
                const data = await res.json();
                const tbody = document.getElementById('fullTxTable');
                if (!tbody) return;
                tbody.innerHTML = '';

                (data.transactions || []).forEach(t => {
                    const tr = document.createElement('tr');
                    tr.className = 'hover:bg-cyan-500/5 transition-colors';
                    const tierBadge = t.risk_tier === 'CRITICAL' ? 'text-rose-500 bg-rose-500/10' : (t.risk_tier === 'HIGH' ? 'text-amber-500 bg-amber-500/10' : 'text-emerald-500 bg-emerald-500/10');
                    tr.innerHTML = `
                        <td class="p-3 font-semibold">${t.tx_id}</td>
                        <td class="p-3 text-muted">${t.date} ${t.time}</td>
                        <td class="p-3">${t.sender_account} &rarr; ${t.receiver_account}</td>
                        <td class="p-3 text-emerald-500 font-bold">$${Number(t.amount).toLocaleString()}</td>
                        <td class="p-3 text-muted">${t.sender_bank_location} &rarr; ${t.receiver_bank_location}</td>
                        <td class="p-3">${t.payment_type}</td>
                        <td class="p-3"><span class="px-2 py-0.5 rounded ${tierBadge} text-[10px] font-bold">${t.risk_tier}</span></td>
                        <td class="p-3 text-right font-bold text-cyan-500">${t.risk_score}</td>
                    `;
                    tbody.appendChild(tr);
                });
            } catch (err) {
                console.error(err);
            }
        }

        // ================= SQL QUERY STUDIO FUNCTIONS =================

        async function loadSQLSchema() {
            try {
                const res = await fetch('/api/sql/schema');
                const data = await res.json();
                const container = document.getElementById('sqlSchemaList');
                if (!container) return;
                container.innerHTML = '';

                for (const [tbl, info] of Object.entries(data.tables || {})) {
                    const div = document.createElement('div');
                    div.className = 'p-2.5 rounded-xl bg-subtle border border-theme hover:border-purple-500/40 cursor-pointer transition-colors';
                    div.onclick = () => insertSQLTable(tbl);
                    div.innerHTML = `
                        <div class="flex items-center justify-between font-bold text-purple-400">
                            <span>📄 ${tbl}</span>
                            <span class="text-[10px] text-muted font-normal">${Number(info.total_records).toLocaleString()} rows</span>
                        </div>
                        <div class="text-[10px] text-muted truncate mt-0.5">${info.columns.map(c => c.name).slice(0, 5).join(', ')}...</div>
                    `;
                    container.appendChild(div);
                }
            } catch (err) {
                console.error(err);
            }
        }

        function insertSQLTable(tbl) {
            const input = document.getElementById('sqlInput');
            input.value = `SELECT * FROM ${tbl} LIMIT 50;`;
            runSQLQuery();
        }

        function loadSQLPreset(preset) {
            const input = document.getElementById('sqlInput');
            if (preset === 'structuring') {
                input.value = `SELECT tx_id, date, time, sender_account, receiver_account, amount, payment_type, risk_score, risk_tier, rule_violations
FROM transactions 
WHERE amount >= 8500 AND amount < 10000 
ORDER BY amount DESC 
LIMIT 50;`;
            } else if (preset === 'jurisdictions') {
                input.value = `SELECT sender_bank_location, receiver_bank_location, COUNT(*) as tx_count, ROUND(SUM(amount), 2) as total_volume, ROUND(AVG(risk_score), 1) as avg_risk
FROM transactions 
WHERE risk_score >= 50.0 
GROUP BY sender_bank_location, receiver_bank_location 
ORDER BY tx_count DESC 
LIMIT 20;`;
            } else if (preset === 'critical_alerts') {
                input.value = `SELECT alert_id, tx_id, sender_account, receiver_account, amount, alert_type, severity, risk_score, status 
FROM alerts 
WHERE severity = 'CRITICAL' AND status = 'NEW' 
ORDER BY risk_score DESC 
LIMIT 50;`;
            } else if (preset === 'top_accounts') {
                input.value = `SELECT sender_account, COUNT(*) as total_transfers, ROUND(SUM(amount), 2) as total_outflow, ROUND(AVG(risk_score), 1) as avg_risk 
FROM transactions 
GROUP BY sender_account 
ORDER BY total_outflow DESC 
LIMIT 20;`;
            } else if (preset === 'schemas') {
                input.value = `SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';`;
            }
            runSQLQuery();
        }

        function handleSQLKeyDown(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                runSQLQuery();
            }
        }

        function clearSQLEditor() {
            document.getElementById('sqlInput').value = '';
            document.getElementById('sqlInput').focus();
        }

        async function runSQLQuery() {
            const query = document.getElementById('sqlInput').value.trim();
            if (!query) return;

            const btn = document.getElementById('runSqlBtn');
            const badge = document.getElementById('sqlExecutionBadge');
            const errBox = document.getElementById('sqlErrorBox');
            const exportBtn = document.getElementById('exportSqlBtn');
            const rowCountEl = document.getElementById('sqlRowCount');

            btn.classList.add('opacity-75');
            badge.innerText = 'Executing query...';
            errBox.classList.add('hidden');

            try {
                const res = await fetch('/api/sql/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: query, limit: 500 })
                });
                const data = await res.json();
                lastSQLResultData = data;

                if (data.status === 'error') {
                    errBox.innerText = 'SQL Execution Error: ' + data.error_message;
                    errBox.classList.remove('hidden');
                    badge.innerText = `Error (${data.execution_time_ms} ms)`;
                    rowCountEl.innerText = '0 rows';
                    exportBtn.classList.add('hidden');
                    return;
                }

                badge.innerText = `⚡ ${data.execution_time_ms} ms • ${data.type}`;
                
                if (data.type === 'SELECT') {
                    rowCountEl.innerText = `${data.row_count} of ${data.total_matching} rows`;
                    renderSQLResultsTable(data.columns, data.rows);
                    if (data.rows.length > 0) exportBtn.classList.remove('hidden');
                    else exportBtn.classList.add('hidden');
                } else {
                    rowCountEl.innerText = `${data.affected_rows} rows affected`;
                    renderSQLResultsTable(['Execution Status', 'Affected Rows'], [[data.message, data.affected_rows]]);
                    exportBtn.classList.add('hidden');
                    refreshData();
                }
            } catch (err) {
                errBox.innerText = 'Network error executing SQL query: ' + err.message;
                errBox.classList.remove('hidden');
            } finally {
                btn.classList.remove('opacity-75');
            }
        }

        function renderSQLResultsTable(columns, rows) {
            const thead = document.querySelector('#sqlResultsTable thead');
            const tbody = document.getElementById('sqlResultsBody');

            let headerHtml = '<tr>';
            columns.forEach(col => {
                headerHtml += `<th class="p-3 text-purple-400 font-bold whitespace-nowrap">${col}</th>`;
            });
            headerHtml += '</tr>';
            thead.innerHTML = headerHtml;

            if (!rows || rows.length === 0) {
                tbody.innerHTML = `<tr><td colspan="${columns.length}" class="p-4 text-center text-muted">Query executed successfully (0 rows returned).</td></tr>`;
                return;
            }

            let bodyHtml = '';
            rows.forEach(row => {
                bodyHtml += '<tr class="hover:bg-purple-500/5 transition-colors">';
                row.forEach(cell => {
                    let displayVal = cell === null ? '<span class="text-muted italic">NULL</span>' : cell;
                    bodyHtml += `<td class="p-2.5 whitespace-nowrap text-xs max-w-xs truncate">${displayVal}</td>`;
                });
                bodyHtml += '</tr>';
            });
            tbody.innerHTML = bodyHtml;
        }

        function exportSQLResultsCSV() {
            if (!lastSQLResultData || !lastSQLResultData.rows || lastSQLResultData.rows.length === 0) return;
            
            const cols = lastSQLResultData.columns;
            const rows = lastSQLResultData.rows;

            let csvContent = "data:text/csv;charset=utf-8," + [
                cols.join(','),
                ...rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))
            ].join('
');

            const encodedUri = encodeURI(csvContent);
            const link = document.createElement("a");
            link.setAttribute("href", encodedUri);
            link.setAttribute("download", `aml_sql_export_${Date.now()}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        function loadScenario(type) {
            if (type === 'structuring') {
                document.getElementById('t_amount').value = 9850.00;
                document.getElementById('t_payment_type').value = 'Cash Deposit';
                document.getElementById('t_sender_loc').value = 'US';
                document.getElementById('t_receiver_loc').value = 'US';
            } else if (type === 'panama') {
                document.getElementById('t_amount').value = 85000.00;
                document.getElementById('t_payment_type').value = 'Wire Transfer';
                document.getElementById('t_sender_loc').value = 'US';
                document.getElementById('t_receiver_loc').value = 'Panama';
            } else if (type === 'pass_through') {
                document.getElementById('t_amount').value = 55000.00;
                document.getElementById('t_payment_type').value = 'Cross-border';
                document.getElementById('t_sender_loc').value = 'UK';
                document.getElementById('t_receiver_loc').value = 'Cayman Islands';
            } else if (type === 'normal') {
                document.getElementById('t_amount').value = 350.00;
                document.getElementById('t_payment_type').value = 'Credit Card';
                document.getElementById('t_sender_loc').value = 'US';
                document.getElementById('t_receiver_loc').value = 'US';
            }
            document.getElementById('txTestForm').dispatchEvent(new Event('submit'));
        }

        async function testTransaction(e) {
            if (e) e.preventDefault();
            const payload = {
                amount: parseFloat(document.getElementById('t_amount').value),
                sender_account: document.getElementById('t_sender').value,
                receiver_account: document.getElementById('t_receiver').value,
                sender_bank_location: document.getElementById('t_sender_loc').value,
                receiver_bank_location: document.getElementById('t_receiver_loc').value,
                payment_type: document.getElementById('t_payment_type').value
            };

            const res = await fetch('/api/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            const evalRes = data.evaluation;

            document.getElementById('resScore').innerText = evalRes.risk_score;
            document.getElementById('resRuleScore').innerText = evalRes.rule_score + '/100';
            document.getElementById('resMLScore').innerText = evalRes.ml_confidence + '%';
            
            const badge = document.getElementById('resTierBadge');
            badge.innerText = evalRes.risk_tier + ' RISK';
            badge.className = `inline-block px-3 py-1 text-xs font-bold rounded-full ${evalRes.risk_tier === 'CRITICAL' ? 'bg-rose-500/20 text-rose-500' : (evalRes.risk_tier === 'HIGH' ? 'bg-amber-500/20 text-amber-500' : 'bg-emerald-500/20 text-emerald-500')}`;

            const ul = document.getElementById('resReasons');
            ul.innerHTML = '';
            evalRes.explanation_reasons.forEach(r => {
                const li = document.createElement('li');
                li.innerText = r;
                ul.appendChild(li);
            });
        }

        async function loadModelMetrics() {
            try {
                const res = await fetch('/api/model/metrics');
                const metrics = await res.json();
                const imps = metrics.feature_importances || {};
                
                const labels = Object.keys(imps).slice(0, 10);
                const values = Object.values(imps).slice(0, 10);

                const isDark = document.documentElement.classList.contains('dark');
                const textColor = isDark ? '#9ca3af' : '#475569';
                const gridColor = isDark ? '#1f2937' : '#cbd5e1';

                const ctxFeat = document.getElementById('featureChart').getContext('2d');
                if (featureChartInstance) featureChartInstance.destroy();
                featureChartInstance = new Chart(ctxFeat, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Gini Feature Importance',
                            data: values,
                            backgroundColor: '#8b5cf6',
                            borderRadius: 6
                        }]
                    },
                    options: {
                        indexAxis: 'y',
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 } } },
                            y: { grid: { display: false }, ticks: { color: textColor, font: { size: 10 } } }
                        }
                    }
                });
            } catch (err) {
                console.error(err);
            }
        }

        function openSarModal(alertId, sender, receiver, amount, typology, risk) {
            document.getElementById('sar_alert_id').value = alertId;
            document.getElementById('sar_primary').value = sender;
            document.getElementById('sar_amount').value = '$' + Number(amount).toLocaleString();
            document.getElementById('sar_typology').value = typology;
            document.getElementById('sar_risk_score').value = risk;
            document.getElementById('sar_narrative').value = `FinCEN SAR Narrative: Suspicious financial pattern matching FATF Typology: ${typology}. Subject Account ${sender} initiated transfers totaling $${Number(amount).toLocaleString()} to Counterparty ${receiver}. Multi-factor risk engine computed composite anomaly score of ${risk}/100. Immediate AML compliance hold and regulator escalation recommended.`;
            
            document.getElementById('sarModal').classList.remove('hidden');
            if (typeof lucide !== 'undefined' && lucide.createIcons) { try { lucide.createIcons(); } catch(e){} }
        }

        function closeSarModal() {
            document.getElementById('sarModal').classList.add('hidden');
        }

        async function submitSarFiling() {
            const payload = {
                alert_id: document.getElementById('sar_alert_id').value,
                primary_account: document.getElementById('sar_primary').value,
                counterparty_account: '9928174822',
                suspicious_amount: parseFloat(document.getElementById('sar_amount').value.replace(/[^0-9.]/g, '')),
                laundering_typology: document.getElementById('sar_typology').value,
                risk_score: parseFloat(document.getElementById('sar_risk_score').value),
                narrative: document.getElementById('sar_narrative').value,
                compliance_officer: 'Senior AML Compliance Officer'
            };

            await fetch('/api/sar/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            closeSarModal();
            loadAlerts();
            refreshData();
            alert('SAR Report successfully submitted and filed with FinCEN Regulatory Network!');
        }

// Global exports for inline HTML onclick handlers
window.switchTab = switchTab;
window.setTheme = setTheme;
window.refreshData = refreshData;
window.loadAlerts = loadAlerts;
window.triageStatus = triageStatus;
window.simulateStream = simulateStream;
window.toggleAutoStream = toggleAutoStream;
window.renderNetworkForAccount = renderNetworkForAccount;
window.loadAccountProfile = loadAccountProfile;
window.searchTransactions = searchTransactions;
window.loadSQLSchema = loadSQLSchema;
window.insertSQLTable = insertSQLTable;
window.loadSQLPreset = loadSQLPreset;
window.handleSQLKeyDown = handleSQLKeyDown;
window.clearSQLEditor = clearSQLEditor;
window.runSQLQuery = runSQLQuery;
window.exportSQLResultsCSV = exportSQLResultsCSV;
window.loadScenario = loadScenario;
window.testTransaction = testTransaction;
window.openSarModal = openSarModal;
window.closeSarModal = closeSarModal;
window.submitSarFiling = submitSarFiling;

window.addEventListener('DOMContentLoaded', function() {
    initTheme();
    refreshData();
    loadModelMetrics();
    searchTransactions();
    loadSQLSchema();
    if (window.lucide && lucide.createIcons) {
        try { if (typeof lucide !== 'undefined' && lucide.createIcons) { try { lucide.createIcons(); } catch(e){} } } catch(e){}
    }
});


function bootApp() {
    try { initTheme(); } catch(e){}
    try { refreshData(); } catch(e){}
    try { loadModelMetrics(); } catch(e){}
    try { searchTransactions(); } catch(e){}
    try { loadSQLSchema(); } catch(e){}
    if (typeof lucide !== 'undefined' && lucide.createIcons) {
        try { lucide.createIcons(); } catch(e){}
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootApp);
} else {
    bootApp();
}
