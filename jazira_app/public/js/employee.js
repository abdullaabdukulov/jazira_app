// Employee DocType uchun Manager-friendly forma
// Fayl: jazira_app/public/js/employee.js

frappe.ui.form.on('Employee', {
    refresh: function(frm) {
        simplify_for_manager(frm);
    },
    
    onload: function(frm) {
        simplify_for_manager(frm);
    }
});

function simplify_for_manager(frm) {
    // Administrator va admin_jazira - to'liq forma
    const full_access_users = ["Administrator", "admin_jazira@jazira.uz"];
    if (full_access_users.includes(frappe.session.user)) {
        return;
    }
    
    // ═══════════════════════════════════════════════════════════════
    // KERAKLI FIELDLAR
    // ═══════════════════════════════════════════════════════════════
    const required_fields = [
        // Asosiy
        'naming_series', 
        'first_name', 
        'middle_name', 
        'last_name',
        'employee_name',
        'gender', 
        'date_of_birth', 
        'date_of_joining', 
        'status', 
        'image',
        
        // Kompaniya
        'company', 
        'designation',
        
        // Davomat - muhim!
        'attendance_device_id', 
        'default_shift',
        
        // Maosh - muhim!
        'ctc',
        'hourly_rate',
        
        // Aloqa
        'cell_number', 
        'personal_email',
        'company_email'
    ];
    
    // ═══════════════════════════════════════════════════════════════
    // YASHIRISH va KO'RSATISH
    // ═══════════════════════════════════════════════════════════════
    
    frm.meta.fields.forEach(function(field) {
        const fn = field.fieldname;
        
        // Section Break va Column Break - o'tkazib yuborish
        if (field.fieldtype === 'Tab Break') {
            // Faqat Overview tab ko'rinsin
            if (fn !== 'overview_tab' && fn !== 'basic_info_tab') {
                frm.set_df_property(fn, 'hidden', 1);
            }
            return;
        }
        
        if (field.fieldtype === 'Section Break' || field.fieldtype === 'Column Break') {
            return;
        }
        
        // Kerakli fieldlarni ko'rsatish, qolganlarini yashirish
        if (required_fields.includes(fn)) {
            frm.set_df_property(fn, 'hidden', 0);
        } else if (fn) {
            frm.set_df_property(fn, 'hidden', 1);
        }
    });
    
    // ═══════════════════════════════════════════════════════════════
    // QOLGAN TABLARNI YASHIRISH
    // ═══════════════════════════════════════════════════════════════
    setTimeout(function() {
        // Barcha tab linklar
        frm.page.wrapper.find('.form-tabs .nav-link').each(function() {
            const tab_text = $(this).text().trim();
            // Faqat Overview qolsin
            if (tab_text && tab_text !== 'Overview') {
                $(this).parent().hide();
            }
        });
    }, 100);
    
    // ═══════════════════════════════════════════════════════════════
    // KERAKLI FIELDLARNI MAJBURIY KO'RSATISH (agar yashirilgan bo'lsa)
    // ═══════════════════════════════════════════════════════════════
    
    // Attendance Device ID
    if (frm.fields_dict['attendance_device_id']) {
        $(frm.fields_dict['attendance_device_id'].wrapper).show();
        frm.set_df_property('attendance_device_id', 'hidden', 0);
    }
    
    // Default Shift
    if (frm.fields_dict['default_shift']) {
        $(frm.fields_dict['default_shift'].wrapper).show();
        frm.set_df_property('default_shift', 'hidden', 0);
    }
    
    // Hourly Rate
    if (frm.fields_dict['hourly_rate']) {
        $(frm.fields_dict['hourly_rate'].wrapper).show();
        frm.set_df_property('hourly_rate', 'hidden', 0);
    }
    
    // Cell Number
    if (frm.fields_dict['cell_number']) {
        $(frm.fields_dict['cell_number'].wrapper).show();
        frm.set_df_property('cell_number', 'hidden', 0);
    }
    
    // Personal Email
    if (frm.fields_dict['personal_email']) {
        $(frm.fields_dict['personal_email'].wrapper).show();
        frm.set_df_property('personal_email', 'hidden', 0);
    }
}