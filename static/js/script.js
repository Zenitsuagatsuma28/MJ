// Tab switching functionality
document.addEventListener('DOMContentLoaded', function() {
    // Navigation tabs
    const navTabs = document.querySelectorAll('.nav-tab');
    const tabContents = document.querySelectorAll('.tab-content');

    navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetTab = tab.getAttribute('data-tab');
            
            navTabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(targetTab).classList.add('active');
        });
    });

    // Method tabs (Direct Text vs URL)
    const methodTabs = document.querySelectorAll('.method-tab');
    const inputSections = document.querySelectorAll('.input-section');

    methodTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetMethod = tab.getAttribute('data-method');
            
            methodTabs.forEach(t => t.classList.remove('active'));
            inputSections.forEach(section => section.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(targetMethod + '-input').classList.add('active');
        });
    });

    // Enter key for job text analysis
    document.getElementById('job-text').addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && e.ctrlKey) {
            analyzeJob();
        }
    });
    
    // Enter key for URL extraction
    document.getElementById('job-url').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            extractFromUrl();
        }
    });
    
    // Enter key for company search
    document.getElementById('company-name').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            searchCompany();
        }
    });

    // ✅ FIXED: Chatbot open/close inside DOMContentLoaded
    document.getElementById("chatbot-button").addEventListener("click", function() {
        document.getElementById("chatbot-popup").style.display = "flex";
    });

    document.getElementById("close-chatbot").addEventListener("click", function() {
        document.getElementById("chatbot-popup").style.display = "none";
    });
});

// Language switching
function changeLanguage(lang) {
    window.location.href = `/?lang=${lang}`;
}

// Show loading overlay
function showLoading() {
    document.getElementById('loading').style.display = 'flex';
}

// Hide loading overlay
function hideLoading() {
    document.getElementById('loading').style.display = 'none';
}

// Show error message
function showError(message) {
    const resultsDiv = document.getElementById('results');
    const resultContent = document.getElementById('result-content');
    
    resultContent.innerHTML = `
        <div class="error-message">
            <i class="fas fa-exclamation-triangle"></i>
            ${message}
        </div>
    `;
    
    resultsDiv.style.display = 'block';
}

// Show success message
function showSuccess(message) {
    const resultsDiv = document.getElementById('results');
    const resultContent = document.getElementById('result-content');
    
    resultContent.innerHTML = `
        <div class="success-message">
            <i class="fas fa-check-circle"></i>
            ${message}
        </div>
    `;
    
    resultsDiv.style.display = 'block';
}

// Analyze job posting from direct text
async function analyzeJob() {
    const jobText = document.getElementById('job-text').value.trim();
    
    if (!jobText) {
        showError('Please enter job posting text to analyze.');
        return;
    }
    
    showLoading();
    
    try {
        const response = await fetch('/detect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ text: jobText })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displayJobResults(data);
        } else {
            showError(data.error || 'An error occurred during analysis.');
        }
    } catch (error) {
        showError('Network error. Please check your connection and try again.');
    } finally {
        hideLoading();
    }
}

// Extract and analyze from URL
async function extractFromUrl() {
    const jobUrl = document.getElementById('job-url').value.trim();
    
    if (!jobUrl) {
        showError('Please enter a job posting URL.');
        return;
    }
    
    showLoading();
    
    try {
        const extractResponse = await fetch('/extract_url', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: jobUrl })
        });
        
        const extractData = await extractResponse.json();
        
        if (!extractResponse.ok) {
            showError(extractData.error || 'Failed to extract text from URL.');
            return;
        }
        
        const analyzeResponse = await fetch('/detect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ text: extractData.text })
        });
        
        const analyzeData = await analyzeResponse.json();
        
        if (analyzeResponse.ok) {
            displayJobResults(analyzeData, extractData.text);
        } else {
            showError(analyzeData.error || 'An error occurred during analysis.');
        }
    } catch (error) {
        showError('Network error. Please check your connection and try again.');
    } finally {
        hideLoading();
    }
}

// Display job analysis results
function displayJobResults(data, extractedText = null) {
    const resultsDiv = document.getElementById('results');
    const resultContent = document.getElementById('result-content');
    const aiAnalysisDiv = document.getElementById('ai-analysis');
    
    const isFake = data.result && typeof data.result === 'string' && data.result.includes('FAKE');
    const resultClass = isFake ? 'fake' : 'real';
    const resultIcon = isFake ? 'fas fa-times-circle' : 'fas fa-check-circle';
    const iconClass = isFake ? 'fake' : 'real';
    
    let html = `
        <div class="result-card ${resultClass}">
            <div class="result-header">
                <i class="result-icon ${iconClass} ${resultIcon}"></i>
                <div>
                    <div class="result-title">${data.result || 'Unknown'}</div>
                    <div class="result-confidence">Confidence: ${Math.min(100, Math.max(0, data.confidence_score || 0)).toFixed(1)}%</div>
                </div>
            </div>
            
            <div class="detail-item">
                <div class="detail-label">Words Analyzed</div>
                <div class="detail-value">${data.word_count}</div>
            </div>
    `;
    
    if (data.pattern_matches && data.pattern_matches.length > 0) {
        html += `
            <div class="pattern-matches">
                <h4><i class="fas fa-exclamation-triangle"></i> Suspicious Patterns Detected</h4>
                <ul class="pattern-list">
        `;
        
        data.pattern_matches.forEach(pattern => {
            html += `<li>${pattern}</li>`;
        });
        
        html += `
                </ul>
            </div>
        `;
    }
    
    if (extractedText) {
        html += `
            <div class="detail-item" style="margin-top: 1rem;">
                <div class="detail-label">Extracted Text Preview</div>
                <div style="max-height: 200px; overflow-y: auto; background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 8px; font-size: 0.9rem; color: #b0b0b0;">
                    ${extractedText.substring(0, 500)}${extractedText.length > 500 ? '...' : ''}
                </div>
            </div>
        `;
    }
    
    html += '</div>';
    
    resultContent.innerHTML = html;
    resultsDiv.style.display = 'block';
    
    if (data.salary_analysis || data.job_quality_score || data.interview_analysis) {
        displayAIAnalysis(data);
        aiAnalysisDiv.style.display = 'block';
    }
    
    window.currentAnalysisData = data;
}

// Display AI Analysis
function displayAIAnalysis(data) {
    if (data.salary_analysis) {
        document.querySelector('#salary-analysis .ai-content').textContent = data.salary_analysis;
    }
    
    if (data.job_quality_score) {
        document.querySelector('#job-quality .ai-content').textContent = data.job_quality_score;
    }
    
    if (data.interview_analysis) {
        document.querySelector('#interview-analysis .ai-content').textContent = data.interview_analysis;
    }
}

// Search company in fraud database
async function searchCompany() {
    const companyName = document.getElementById('company-name').value.trim();
    
    if (!companyName) {
        showCompanyError('Please enter a company name to search.');
        return;
    }
    
    showLoading();
    
    try {
        const response = await fetch('/search_company', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ company_name: companyName })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            if (data.found) {
                displayCompanyResults(data);
            } else {
                showCompanyMessage(data.message, 'info');
            }
        } else {
            showCompanyError(data.error || 'An error occurred during search.');
        }
    } catch (error) {
        showCompanyError('Network error. Please check your connection and try again.');
    } finally {
        hideLoading();
    }
}

// Display company search results
function displayCompanyResults(data) {
    const resultsDiv = document.getElementById('company-results');
    const resultContent = document.getElementById('company-content');
    
    const isFraud = data.is_fraud;
    const resultClass = isFraud ? 'fraud' : 'legit';
    const statusText = isFraud ? 'FRAUD DETECTED' : 'LEGITIMATE COMPANY';
    const statusClass = isFraud ? 'fraud' : 'legit';
    const icon = isFraud ? 'fas fa-exclamation-triangle' : 'fas fa-check-circle';
    
    let html = `
        <div class="company-card ${resultClass}">
            <div class="company-header">
                <div>
                    <div class="company-name">${data.company_data.name}</div>
                    <div class="company-status ${statusClass}">
                        <i class="${icon}"></i>
                        ${statusText}
                    </div>
                </div>
            </div>
            
            <div class="company-details">
                <div class="detail-item">
                    <div class="detail-label">Fraud Score</div>
                    <div class="detail-value">${data.company_data.fraud_score}/100</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Reports</div>
                    <div class="detail-value">${data.company_data.reports}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Last Updated</div>
                    <div class="detail-value">${data.company_data.last_updated}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Domain Age</div>
                    <div class="detail-value">${data.company_data.domain_age}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Social Media</div>
                    <div class="detail-value">${data.company_data.social_media}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Contact Verification</div>
                    <div class="detail-value">${data.company_data.contact_verification}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Industry</div>
                    <div class="detail-value">${data.company_data.industry}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Location</div>
                    <div class="detail-value">${data.company_data.location}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Website</div>
                    <div class="detail-value">${data.company_data.website}</div>
                </div>
            </div>
            
            ${data.company_data.red_flags ? `
                <div class="detail-item" style="margin-top: 1rem;">
                    <div class="detail-label">Red Flags</div>
                    <div class="detail-value">
                        <ul style="margin: 0; padding-left: 1rem;">
                            ${data.company_data.red_flags.map(flag => `<li>${flag}</li>`).join('')}
                        </ul>
                    </div>
                </div>
            ` : ''}
            
            ${data.company_data.green_flags ? `
                <div class="detail-item" style="margin-top: 1rem;">
                    <div class="detail-label">Green Flags</div>
                    <div class="detail-value">
                        <ul style="margin: 0; padding-left: 1rem;">
                            ${data.company_data.green_flags.map(flag => `<li>${flag}</li>`).join('')}
                        </ul>
                    </div>
                </div>
            ` : ''}
            
            ${data.partial_match ? '<div class="detail-item"><div class="detail-label">Note</div><div class="detail-value">Partial match found</div></div>' : ''}
        </div>
    `;
    
    resultContent.innerHTML = html;
    resultsDiv.style.display = 'block';
}

// Show company error message
function showCompanyError(message) {
    const resultsDiv = document.getElementById('company-results');
    const resultContent = document.getElementById('company-content');
    
    resultContent.innerHTML = `
        <div class="error-message">
            <i class="fas fa-exclamation-triangle"></i>
            ${message}
        </div>
    `;
    
    resultsDiv.style.display = 'block';
}

// Show company info message
function showCompanyMessage(message, type = 'info') {
    const resultsDiv = document.getElementById('company-results');
    const resultContent = document.getElementById('company-content');
    
    const messageClass = type === 'info' ? 'success-message' : 'error-message';
    const icon = type === 'info' ? 'fas fa-info-circle' : 'fas fa-exclamation-triangle';
    
    resultContent.innerHTML = `
        <div class="${messageClass}">
            <i class="${icon}"></i>
            ${message}
        </div>
    `;
    
    resultsDiv.style.display = 'block';
}

// Export PDF
async function exportPDF() {
    if (!window.currentAnalysisData) {
        showError('No analysis data available for export.');
        return;
    }
    
    showLoading();
    
    try {
        const response = await fetch('/export_pdf', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ analysis_data: window.currentAnalysisData })
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `sniftern_analysis_report_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } else {
            const data = await response.json();
            showError(data.error || 'Failed to generate PDF report.');
        }
    } catch (error) {
        showError('Network error. Please check your connection and try again.');
    } finally {
        hideLoading();
    }
}

// Send chatbot message
function sendChatMessage() {
    const input = document.getElementById("chatbot-input");
    const message = input.value.trim();
    if (!message) return;

    const messagesDiv = document.getElementById("chatbot-messages");

    const userMsg = document.createElement("div");
    userMsg.className = "user-message";
    userMsg.textContent = message;
    messagesDiv.appendChild(userMsg);

    const botMsg = document.createElement("div");
    botMsg.className = "bot-message";
    botMsg.textContent = "I'm analyzing your query...";
    messagesDiv.appendChild(botMsg);

    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    input.value = "";
}