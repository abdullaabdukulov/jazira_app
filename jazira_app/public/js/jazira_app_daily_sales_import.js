/**
 * Jazira App Daily Sales Import - Client Script
 * ERPNext v15 / Frappe v15
 * Version 3.0 FINAL - Clean & Bug-free
 */

frappe.ui.form.on('Jazira App Daily Sales Import', {
    
    refresh(frm) {
        frm.trigger('setup_buttons');
        frm.trigger('set_warehouse_filter');
        frm.trigger('validate_prerequisites');
        frm.trigger('format_stock_entry_links');
        
        // Status indicator
        const colors = { Draft: 'blue', Processing: 'orange', Processed: 'green', Failed: 'red' };
        frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || 'gray');
    },
    
    company(frm) {
        if (!frm.doc.company) {
            frm.set_value('source_warehouse', '');
            return;
        }
        
        // Debounce - prevent duplicate calls
        clearTimeout(frm._company_timer);
        frm._company_timer = setTimeout(() => {
            frm.trigger('auto_set_warehouse');
        }, 300);
    },
    
    auto_set_warehouse(frm) {
        // Skip if already loading
        if (frm._loading) return;
        frm._loading = true;
        
        frappe.call({
            method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.get_default_warehouse',
            args: { company: frm.doc.company },
            callback(r) {
                frm._loading = false;
                
                if (r.message && r.message.source_warehouse) {
                    const wh = r.message.source_warehouse;
                    
                    // Skip if same value
                    if (frm.doc.source_warehouse === wh) {
                        frm.trigger('validate_prerequisites');
                        return;
                    }
                    
                    frm._skip_wh_trigger = true;
                    frm.set_value('source_warehouse', wh).then(() => {
                        frappe.show_alert({
                            message: __('Default warehouse: {0}', [wh]),
                            indicator: 'green'
                        });
                        frm._skip_wh_trigger = false;
                        frm.trigger('validate_prerequisites');
                    });
                } else {
                    frm.trigger('validate_prerequisites');
                }
            },
            error() {
                frm._loading = false;
            }
        });
        
        frm.trigger('set_warehouse_filter');
    },
    
    source_warehouse(frm) {
        if (!frm._skip_wh_trigger) {
            frm.trigger('validate_prerequisites');
        }
    },
    
    posting_date(frm) {
        frm.trigger('validate_prerequisites');
    },
    
    excel_file(frm) {
        if (frm.doc.excel_file && frm.doc.status === 'Draft') {
            frm.save().then(() => frm.trigger('show_preview'));
        }
    },
    
    set_warehouse_filter(frm) {
        frm.set_query('source_warehouse', () => ({
            filters: { company: frm.doc.company || '', is_group: 0 }
        }));
    },
    
    validate_prerequisites(frm) {
        const valid = frm.doc.company && frm.doc.source_warehouse && frm.doc.posting_date;
        
        frm.set_df_property('excel_file', 'read_only', valid ? 0 : 1);
        frm.set_df_property('excel_file', 'description', valid 
            ? 'POS hisoboti Excel fayli (.xlsx)'
            : '<span style="color:red;">⚠️ Avval Company, Ombor va Sana tanlang!</span>'
        );
    },
    
    format_stock_entry_links(frm) {
        if (!frm.doc.stock_entry || frm.doc.status !== 'Processed') return;
        
        const links = frm.doc.stock_entry.split(',')
            .map(s => s.trim())
            .filter(s => s)
            .map(se => `<a href="/app/stock-entry/${se}">${se}</a>`)
            .join('<br>');
        
        setTimeout(() => {
            const el = frm.fields_dict.stock_entry?.$wrapper?.find('.like-disabled-input, .control-value');
            if (el?.length) el.html(links);
        }, 100);
    },
    
    // =========================================================================
    // BUTTONS
    // =========================================================================
    
    setup_buttons(frm) {
        frm.clear_custom_buttons();
        
        if (frm.doc.status === 'Draft' && frm.doc.excel_file) {
            frm.add_custom_button(__('📋 Preview'), () => frm.trigger('show_preview'), __('Actions'));
            frm.add_custom_button(__('✓ Validate'), () => frm.trigger('validate_items'), __('Actions'));
            frm.add_custom_button(__('▶ Process Import'), () => frm.trigger('process_import')).addClass('btn-primary');
        }
        
        if (frm.doc.status === 'Processed') {
            frm.add_custom_button(__('✕ Cancel Import'), () => frm.trigger('cancel_import')).addClass('btn-danger');
            
            // Stock Entry buttons
            if (frm.doc.stock_entry) {
                const entries = frm.doc.stock_entry.split(',').map(s => s.trim()).filter(s => s);
                entries.forEach((se, i) => {
                    frm.add_custom_button(
                        entries.length === 1 ? __('Manufacture SE') : __(`Manufacture ${i + 1}`),
                        () => frappe.set_route('Form', 'Stock Entry', se),
                        entries.length === 1 ? __('View') : __('Manufacture SEs')
                    );
                });
            }
            
            if (frm.doc.sales_invoice) {
                frm.add_custom_button(__('Sales Invoice'), 
                    () => frappe.set_route('Form', 'Sales Invoice', frm.doc.sales_invoice), __('View'));
            }
        }
        
        if (frm.doc.status === 'Failed') {
            frm.add_custom_button(__('🔄 Retry'), () => {
                frm.set_value('status', 'Draft');
                frm.set_value('error_log', '');
                frm.set_value('import_log', '');
                frm.save().then(() => frm.trigger('process_import'));
            }).addClass('btn-warning');
        }
    },
    
    // =========================================================================
    // PREVIEW
    // =========================================================================
    
    show_preview(frm) {
        frappe.call({
            method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.get_preview_data',
            args: { doc_name: frm.doc.name },
            freeze: true,
            freeze_message: __('Excel o\'qilmoqda...'),
            callback(r) {
                if (r.message?.success) {
                    frm.trigger('render_preview', r.message);
                } else {
                    frappe.msgprint({
                        title: __('Xato'),
                        indicator: 'red',
                        message: r.message?.message || __('Preview yuklashda xato')
                    });
                }
            }
        });
    },
    
    render_preview(frm, data) {
        const items = data.items || [];
        const s = data.summary || {};
        
        const rows = items.map((item, i) => {
            let badge = '';
            if (!item.found) badge = '<span class="badge badge-danger">NOT FOUND</span>';
            else if (item.has_bom) badge = '<span class="badge badge-primary">MANUFACTURE</span>';
            else badge = '<span class="badge badge-secondary">DIRECT SALE</span>';
            
            return `<tr class="${item.found ? '' : 'table-danger'}">
                <td>${i + 1}</td>
                <td>${item.item_name}${item.bom ? `<br><small class="text-muted">${item.bom}</small>` : ''}</td>
                <td>${item.item_code || '-'}</td>
                <td class="text-right">${item.qty}</td>
                <td class="text-right">${format_currency(item.rate, 'UZS')}</td>
                <td class="text-right">${format_currency(item.qty * item.rate, 'UZS')}</td>
                <td>${badge}</td>
            </tr>`;
        }).join('');
        
        new frappe.ui.Dialog({
            title: __('Excel Preview'),
            size: 'extra-large',
            fields: [{
                fieldtype: 'HTML',
                fieldname: 'html',
                options: `
                    <div class="row mb-3">
                        <div class="col"><div class="card bg-primary text-white text-center p-2"><h4 class="mb-0">${s.total_items || 0}</h4><small>Jami</small></div></div>
                        <div class="col"><div class="card bg-success text-white text-center p-2"><h4 class="mb-0">${s.found || 0}</h4><small>Topildi</small></div></div>
                        <div class="col"><div class="card bg-danger text-white text-center p-2"><h4 class="mb-0">${s.not_found || 0}</h4><small>Topilmadi</small></div></div>
                        <div class="col"><div class="card bg-info text-white text-center p-2"><h4 class="mb-0">${s.with_bom || 0}</h4><small>BOM</small></div></div>
                        <div class="col"><div class="card bg-secondary text-white text-center p-2"><h4 class="mb-0">${s.without_bom || 0}</h4><small>No BOM</small></div></div>
                    </div>
                    <p><strong>💰 Jami:</strong> ${format_currency(s.total_amount || 0, 'UZS')}</p>
                    <div class="table-responsive" style="max-height:300px;overflow-y:auto;">
                        <table class="table table-sm table-bordered">
                            <thead class="thead-dark"><tr>
                                <th>#</th><th>Nomi</th><th>Item Code</th>
                                <th class="text-right">Qty</th><th class="text-right">Rate</th>
                                <th class="text-right">Amount</th><th>Type</th>
                            </tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>`
            }]
        }).show();
    },
    
    // =========================================================================
    // VALIDATE
    // =========================================================================
    
    validate_items(frm) {
        frappe.call({
            method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.validate_excel_items',
            args: { doc_name: frm.doc.name },
            freeze: true,
            freeze_message: __('Tekshirilmoqda...'),
            callback(r) {
                if (!r.message) return;
                const d = r.message;
                
                if (d.success) {
                    frappe.msgprint({
                        title: __('✅ Validation OK'),
                        indicator: 'green',
                        message: `<p><strong>${d.items.length}</strong> ta item topildi</p>
                                  <p>Jami: <strong>${format_currency(d.total_amount, 'UZS')}</strong></p>`
                    });
                } else {
                    const errors = (d.errors || []).map(e => `<li>Qator ${e.row}: ${e.error}</li>`).join('');
                    frappe.msgprint({
                        title: __('❌ Xatolar'),
                        indicator: 'red',
                        message: `<ul>${errors}</ul>`
                    });
                }
            }
        });
    },
    
    // =========================================================================
    // PROCESS IMPORT
    // =========================================================================
    
    process_import(frm) {
        const dlg = new frappe.ui.Dialog({
            title: __('Import tasdiqlash'),
            fields: [{
                fieldtype: 'HTML',
                options: `
                    <p><strong>Company:</strong> ${frm.doc.company}</p>
                    <p><strong>Ombor:</strong> ${frm.doc.source_warehouse}</p>
                    <p><strong>Sana:</strong> ${frm.doc.posting_date}</p>
                    <div class="alert alert-info mt-3">
                        <strong>Workflow:</strong><br>
                        1️⃣ BOM li → Manufacture<br>
                        2️⃣ Barcha → Sales Invoice (Update Stock ON)
                    </div>`
            }],
            primary_action_label: __('✓ Import qilish'),
            primary_action() {
                dlg.hide();
                
                frappe.call({
                    method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.process_import',
                    args: { doc_name: frm.doc.name, background: false },
                    freeze: true,
                    freeze_message: __('Import jarayoni...'),
                    callback(r) {
                        if (!r.message) return;
                        const res = r.message;
                        
                        if (res.success) {
                            const seLinks = (res.stock_entries || [])
                                .map((se, i) => `<p>🏭 <a href="/app/stock-entry/${se}">Manufacture ${i + 1}: ${se}</a></p>`)
                                .join('') || '<p><em>Manufacture yo\'q</em></p>';
                            
                            frappe.msgprint({
                                title: __('✅ Muvaffaqiyatli'),
                                indicator: 'green',
                                message: `
                                    <p>✅ <strong>${res.total_items}</strong> ta item</p>
                                    <p>🏭 BOM: <strong>${res.items_with_bom}</strong> | 📦 Direct: <strong>${res.items_without_bom}</strong></p>
                                    <p>💰 Jami: <strong>${format_currency(res.total_amount, 'UZS')}</strong></p>
                                    <hr>${seLinks}
                                    <p>📄 <a href="/app/sales-invoice/${res.sales_invoice}">Sales Invoice: ${res.sales_invoice}</a></p>`
                            });
                        } else {
                            frappe.msgprint({ title: __('❌ Xato'), indicator: 'red', message: res.message });
                        }
                        frm.reload_doc();
                    }
                });
            }
        });
        dlg.show();
    },
    
    // =========================================================================
    // CANCEL IMPORT
    // =========================================================================
    
    cancel_import(frm) {
        const seCount = frm.doc.stock_entry ? frm.doc.stock_entry.split(',').filter(s => s.trim()).length : 0;
        
        const dlg = new frappe.ui.Dialog({
            title: __('Import bekor qilish'),
            fields: [{
                fieldtype: 'HTML',
                options: `
                    <p><strong>Bekor qilinadigan hujjatlar:</strong></p>
                    <p>📄 Sales Invoice: ${frm.doc.sales_invoice || 'N/A'}</p>
                    <p>🏭 Stock Entries (${seCount} ta): ${frm.doc.stock_entry || 'N/A'}</p>
                    <p class="text-danger mt-3"><strong>⚠️ Bu amalni ortga qaytarib bo'lmaydi!</strong></p>`
            }],
            primary_action_label: __('✓ Bekor qilish'),
            primary_action() {
                dlg.hide();
                
                frappe.call({
                    method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.cancel_import',
                    args: { doc_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Bekor qilinmoqda...'),
                    callback(r) {
                        if (r.message?.success) {
                            frappe.show_alert({ message: __('Import bekor qilindi'), indicator: 'green' });
                        } else {
                            frappe.msgprint({ title: __('Xato'), indicator: 'red', message: r.message?.message });
                        }
                        frm.reload_doc();
                    }
                });
            }
        });
        dlg.show();
    }
});