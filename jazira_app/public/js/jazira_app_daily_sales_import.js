/**
 * Jazira App Daily Sales Import - Client Script
 * ERPNext v15 / Frappe v15
 * Version 2.1 - VARIANT A: Single Warehouse (Restoran)
 */

frappe.ui.form.on('Jazira App Daily Sales Import', {
    
    refresh: function(frm) {
        frm.trigger('setup_buttons');
        frm.trigger('setup_realtime');
        frm.trigger('show_status_indicator');
        frm.trigger('set_warehouse_filter');
        frm.trigger('validate_prerequisites');
        frm.trigger('format_stock_entry_links');
    },
    
    // =========================================================================
    // FORMAT STOCK ENTRY LINKS
    // =========================================================================
    
    format_stock_entry_links: function(frm) {
        if (frm.doc.stock_entry && frm.doc.status === 'Processed') {
            let se_names = frm.doc.stock_entry.split(',').map(s => s.trim()).filter(s => s);
            
            if (se_names.length > 0) {
                let links_html = se_names.map(se_name => 
                    `<a href="/app/stock-entry/${se_name}" style="margin-right: 10px;">${se_name}</a>`
                ).join('<br>');
                
                // Update the field display
                setTimeout(() => {
                    let field_wrapper = frm.fields_dict.stock_entry.$wrapper;
                    let control_value = field_wrapper.find('.like-disabled-input, .control-value');
                    if (control_value.length) {
                        control_value.html(links_html);
                    }
                }, 100);
            }
        }
    },
    
    // =========================================================================
    // COMPANY CHANGE - Auto-fill warehouse
    // =========================================================================
    
    company: function(frm) {
        if (!frm.doc.company) {
            frm.set_value('source_warehouse', '');
            return;
        }
        
        // Check if current warehouse belongs to new company
        if (frm.doc.source_warehouse) {
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Warehouse',
                    fieldname: 'company',
                    filters: { name: frm.doc.source_warehouse }
                },
                callback: function(r) {
                    if (r.message && r.message.company !== frm.doc.company) {
                        // Warehouse belongs to different company - replace
                        frappe.show_alert({
                            message: __('Warehouse boshqa kompaniyaga tegishli. Yangilanmoqda...'),
                            indicator: 'orange'
                        });
                        frm.trigger('set_default_warehouse');
                    }
                }
            });
        } else {
            // No warehouse set - get default
            frm.trigger('set_default_warehouse');
        }
        
        frm.trigger('set_warehouse_filter');
    },
    
    set_default_warehouse: function(frm) {
        frappe.call({
            method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.get_default_warehouse',
            args: { company: frm.doc.company },
            callback: function(r) {
                if (r.message && r.message.source_warehouse) {
                    frm.set_value('source_warehouse', r.message.source_warehouse);
                    frappe.show_alert({
                        message: __('Default warehouse: {0}', [r.message.source_warehouse]),
                        indicator: 'green'
                    });
                }
            }
        });
    },
    
    source_warehouse: function(frm) {
        frm.trigger('validate_prerequisites');
    },
    
    posting_date: function(frm) {
        frm.trigger('validate_prerequisites');
    },
    
    excel_file: function(frm) {
        if (frm.doc.excel_file) {
            frm.trigger('on_excel_uploaded');
        }
    },
    
    // =========================================================================
    // WAREHOUSE FILTER
    // =========================================================================
    
    set_warehouse_filter: function(frm) {
        frm.set_query('source_warehouse', function() {
            return {
                filters: {
                    'company': frm.doc.company || '',
                    'is_group': 0
                }
            };
        });
    },
    
    // =========================================================================
    // VALIDATION
    // =========================================================================
    
    validate_prerequisites: function(frm) {
        let valid = frm.doc.company && 
                    frm.doc.source_warehouse && 
                    frm.doc.posting_date;
        
        if (!valid) {
            frm.set_df_property('excel_file', 'read_only', 1);
            frm.set_df_property('excel_file', 'description', 
                '<span style="color: red;">⚠️ Avval Company, Oshxona Ombori va Posting Date tanlang!</span>');
        } else {
            frm.set_df_property('excel_file', 'read_only', 0);
            frm.set_df_property('excel_file', 'description', 
                'POS hisoboti Excel fayli (.xlsx)');
        }
    },
    
    on_excel_uploaded: function(frm) {
        if (frm.doc.status !== 'Draft') {
            frappe.msgprint(__('Import allaqachon bajarilgan'));
            return;
        }
        
        frm.save().then(() => {
            frm.trigger('show_preview');
        });
    },
    
    // =========================================================================
    // BUTTONS
    // =========================================================================
    
    setup_buttons: function(frm) {
        frm.clear_custom_buttons();
        
        if (frm.doc.status === 'Draft') {
            if (frm.doc.excel_file) {
                frm.add_custom_button(__('📋 Preview'), function() {
                    frm.trigger('show_preview');
                }, __('Actions'));
                
                frm.add_custom_button(__('✓ Validate'), function() {
                    frm.trigger('validate_items');
                }, __('Actions'));
                
                frm.add_custom_button(__('▶ Process Import'), function() {
                    frm.trigger('process_import');
                }).addClass('btn-primary');
            }
        }
        
        if (frm.doc.status === 'Processed') {
            frm.add_custom_button(__('✕ Cancel Import'), function() {
                frm.trigger('cancel_import');
            }).addClass('btn-danger');
            
            if (frm.doc.stock_entry) {
                // Multiple Stock Entries - show dropdown or first one
                let se_names = frm.doc.stock_entry.split(',').map(s => s.trim()).filter(s => s);
                
                if (se_names.length === 1) {
                    frm.add_custom_button(__('Manufacture SE'), function() {
                        frappe.set_route('Form', 'Stock Entry', se_names[0]);
                    }, __('View'));
                } else if (se_names.length > 1) {
                    // Multiple - add dropdown
                    se_names.forEach((se_name, idx) => {
                        frm.add_custom_button(__(`Manufacture ${idx + 1}`), function() {
                            frappe.set_route('Form', 'Stock Entry', se_name);
                        }, __('Manufacture SEs'));
                    });
                }
            }
            
            if (frm.doc.sales_invoice) {
                frm.add_custom_button(__('Sales Invoice'), function() {
                    frappe.set_route('Form', 'Sales Invoice', frm.doc.sales_invoice);
                }, __('View'));
            }
        }
        
        if (frm.doc.status === 'Failed') {
            frm.add_custom_button(__('🔄 Retry'), function() {
                frm.set_value('status', 'Draft');
                frm.set_value('error_log', '');
                frm.set_value('import_log', '');
                frm.save().then(() => {
                    frm.trigger('process_import');
                });
            }).addClass('btn-warning');
        }
    },
    
    show_status_indicator: function(frm) {
        let status_colors = {
            'Draft': 'blue',
            'Processing': 'orange',
            'Processed': 'green',
            'Failed': 'red'
        };
        
        let color = status_colors[frm.doc.status] || 'gray';
        frm.page.set_indicator(__(frm.doc.status), color);
    },
    
    setup_realtime: function(frm) {
        frappe.realtime.on('restaurant_import_success', function(data) {
            if (data.doc_name === frm.doc.name) {
                frappe.show_alert({
                    message: __('Import muvaffaqiyatli bajarildi!'),
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        });
        
        frappe.realtime.on('restaurant_import_failed', function(data) {
            if (data.doc_name === frm.doc.name) {
                frappe.msgprint({
                    title: __('Import xatosi'),
                    indicator: 'red',
                    message: data.error || data.result?.message
                });
                frm.reload_doc();
            }
        });
    },
    
    // =========================================================================
    // ACTIONS
    // =========================================================================
    
    show_preview: function(frm) {
        frappe.call({
            method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.get_preview_data',
            args: { doc_name: frm.doc.name },
            freeze: true,
            freeze_message: __('Excel o\'qilmoqda...'),
            callback: function(r) {
                if (r.message && r.message.success) {
                    frm.trigger('render_preview_dialog', r.message);
                } else {
                    frappe.msgprint({
                        title: __('Xato'),
                        indicator: 'red',
                        message: r.message ? r.message.message : __('Preview yuklashda xato')
                    });
                }
            }
        });
    },
    
    render_preview_dialog: function(frm, data) {
        let items = data.items || [];
        let summary = data.summary || {};
        
        let rows_html = items.map((item, idx) => {
            let type_badge = '';
            if (!item.found) {
                type_badge = '<span class="badge badge-danger">NOT FOUND</span>';
            } else if (item.has_bom) {
                type_badge = '<span class="badge badge-primary">MANUFACTURE</span>';
            } else {
                type_badge = '<span class="badge badge-secondary">DIRECT SALE</span>';
            }
            
            let bom_info = item.bom ? `<br><small class="text-muted">${item.bom}</small>` : '';
            
            return `
                <tr class="${item.found ? '' : 'table-danger'}">
                    <td>${idx + 1}</td>
                    <td>${item.row_num}</td>
                    <td>${item.item_name}${bom_info}</td>
                    <td>${item.item_code || '-'}</td>
                    <td class="text-right">${item.qty}</td>
                    <td class="text-right">${format_currency(item.rate, 'UZS')}</td>
                    <td class="text-right">${format_currency(item.qty * item.rate, 'UZS')}</td>
                    <td>${type_badge}</td>
                </tr>
            `;
        }).join('');
        
        let dialog = new frappe.ui.Dialog({
            title: __('Excel Preview - Bitta Ombor Workflow'),
            size: 'extra-large',
            fields: [{ fieldtype: 'HTML', fieldname: 'preview_html' }]
        });
        
        let html = `
            <div class="mb-4">
                <div class="row">
                    <div class="col-md-2">
                        <div class="card bg-primary text-white text-center p-2">
                            <h4 class="mb-0">${summary.total_items || 0}</h4>
                            <small>Jami</small>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="card bg-success text-white text-center p-2">
                            <h4 class="mb-0">${summary.found || 0}</h4>
                            <small>Topildi</small>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="card bg-danger text-white text-center p-2">
                            <h4 class="mb-0">${summary.not_found || 0}</h4>
                            <small>Topilmadi</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card bg-info text-white text-center p-2">
                            <h4 class="mb-0">${summary.with_bom || 0}</h4>
                            <small>BOM (Manufacture)</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card bg-secondary text-white text-center p-2">
                            <h4 class="mb-0">${summary.without_bom || 0}</h4>
                            <small>No BOM (Direct)</small>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="alert alert-success">
                <strong>🏪 Bitta Ombor Workflow:</strong><br>
                <span class="text-muted">Hammasi <strong>${frm.doc.source_warehouse}</strong> omborida:</span><br>
                1️⃣ <strong>Manufacture:</strong> Xomashyo (−) → Tayyor mahsulot (+)<br>
                2️⃣ <strong>Sales Invoice:</strong> Tayyor mahsulot (−) [Update Stock ON]
            </div>
            
            <div class="mb-3">
                <strong>💰 Jami summa:</strong> ${format_currency(summary.total_amount || 0, 'UZS')}
            </div>
            
            <div class="table-responsive" style="max-height: 350px; overflow-y: auto;">
                <table class="table table-sm table-bordered table-hover">
                    <thead class="thead-dark" style="position: sticky; top: 0;">
                        <tr>
                            <th>#</th>
                            <th>Row</th>
                            <th>Наименование</th>
                            <th>Item Code</th>
                            <th class="text-right">Qty</th>
                            <th class="text-right">Rate</th>
                            <th class="text-right">Amount</th>
                            <th>Type</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows_html}
                    </tbody>
                </table>
            </div>
        `;
        
        dialog.fields_dict.preview_html.$wrapper.html(html);
        dialog.show();
    },
    
    validate_items: function(frm) {
        frappe.call({
            method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.validate_excel_items',
            args: { doc_name: frm.doc.name },
            freeze: true,
            freeze_message: __('Tekshirilmoqda...'),
            callback: function(r) {
                if (r.message) {
                    let data = r.message;
                    
                    if (data.success) {
                        frappe.msgprint({
                            title: __('✅ Validation Success'),
                            indicator: 'green',
                            message: `
                                <p><strong>${data.items.length}</strong> ta item topildi</p>
                                <p>Jami: <strong>${format_currency(data.total_amount, 'UZS')}</strong></p>
                            `
                        });
                    } else {
                        let errors_html = (data.errors || []).map(e => 
                            `<li><strong>Qator ${e.row}:</strong> ${e.error}</li>`
                        ).join('');
                        
                        frappe.msgprint({
                            title: __('❌ Validation Errors'),
                            indicator: 'red',
                            message: `<ul>${errors_html}</ul>`
                        });
                    }
                }
            }
        });
    },
    
    process_import: function(frm) {
        let workflow_info = `
            <div class="alert alert-success mb-3">
                <strong>🏪 Bitta Ombor Workflow:</strong><br>
                1️⃣ BOM li → Manufacture (${frm.doc.source_warehouse})<br>
                2️⃣ Barcha → Sales Invoice (Update Stock ON)
            </div>
        `;
        
        frappe.confirm(
            __(`Import bajarilsinmi?<br><br>
                <strong>Company:</strong> ${frm.doc.company}<br>
                <strong>Ombor:</strong> ${frm.doc.source_warehouse}<br>
                <strong>Sana:</strong> ${frm.doc.posting_date}<br><br>
                ${workflow_info}
            `),
            function() {
                frappe.call({
                    method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.process_import',
                    args: {
                        doc_name: frm.doc.name,
                        background: false
                    },
                    freeze: true,
                    freeze_message: __('Import jarayoni... (Manufacture → Sales Invoice)'),
                    callback: function(r) {
                        if (r.message) {
                            let result = r.message;
                            
                            if (result.success) {
                                frappe.show_alert({
                                    message: __('Import muvaffaqiyatli!'),
                                    indicator: 'green'
                                });
                                
                                // Build Stock Entries links
                                let stock_entries_html = '';
                                if (result.stock_entries && result.stock_entries.length > 0) {
                                    stock_entries_html = result.stock_entries.map((se, idx) => 
                                        `<p>🏭 <a href="/app/stock-entry/${se}">Manufacture ${idx + 1}: ${se}</a></p>`
                                    ).join('');
                                } else {
                                    stock_entries_html = '<p><em>Manufacture yaratilmadi (BOM yo\'q)</em></p>';
                                }
                                
                                frappe.msgprint({
                                    title: __('✅ Import natijasi'),
                                    indicator: 'green',
                                    message: `
                                        <p>✅ <strong>${result.total_items}</strong> ta item import qilindi</p>
                                        <p>🏭 BOM bilan (Manufacture): <strong>${result.items_with_bom}</strong></p>
                                        <p>📦 BOMsiz (Direct Sale): <strong>${result.items_without_bom}</strong></p>
                                        <p>💰 Jami: <strong>${format_currency(result.total_amount, 'UZS')}</strong></p>
                                        <hr>
                                        ${stock_entries_html}
                                        <p>📄 <a href="/app/sales-invoice/${result.sales_invoice}">Sales Invoice: ${result.sales_invoice}</a></p>
                                    `
                                });
                                
                                frm.reload_doc();
                            } else {
                                frappe.msgprint({
                                    title: __('❌ Import xatosi'),
                                    indicator: 'red',
                                    message: result.message
                                });
                                frm.reload_doc();
                            }
                        }
                    }
                });
            }
        );
    },
    
    cancel_import: function(frm) {
        let se_info = frm.doc.stock_entry || 'N/A';
        let se_count = frm.doc.stock_entry ? frm.doc.stock_entry.split(',').length : 0;
        
        frappe.confirm(
            __(`Import bekor qilinsinmi?<br><br>
                <strong>Bekor qilinadigan hujjatlar:</strong><br>
                📄 Sales Invoice: ${frm.doc.sales_invoice || 'N/A'}<br>
                🏭 Stock Entries (${se_count} ta): ${se_info}
            `),
            function() {
                frappe.call({
                    method: 'jazira_app.jazira_app.doctype.jazira_app_daily_sales_import.jazira_app_daily_sales_import.cancel_import',
                    args: { doc_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Bekor qilinmoqda...'),
                    callback: function(r) {
                        if (r.message) {
                            if (r.message.success) {
                                frappe.show_alert({
                                    message: __('Import bekor qilindi'),
                                    indicator: 'green'
                                });
                            } else {
                                frappe.msgprint({
                                    title: __('Xato'),
                                    indicator: 'red',
                                    message: r.message.message
                                });
                            }
                            frm.reload_doc();
                        }
                    }
                });
            }
        );
    }
});