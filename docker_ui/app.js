const API = 'http://127.0.0.1:8001';
const $ = (id) => document.getElementById(id);

function itemRow(value = {}) {
  const row = document.createElement('div');
  row.className = 'item';
  row.innerHTML = `
    <div class="item-grid">
      <label>Tên món<input data-field="name" value="${value.name || ''}"></label>
      <label>Giá<input data-field="price" value="${value.price || ''}"></label>
    </div>
    <label>Nhóm món<input data-field="section" value="${value.section || 'Món chính'}"></label>
    <label>Mô tả<input data-field="description" value="${value.description || ''}"></label>
    <label>Ảnh có sẵn<input data-field="image_path" placeholder="D:\\Images\\dish.png" value="${value.image_path || ''}"></label>
    <label>Prompt tạo ảnh<textarea data-field="image_prompt">${value.image_prompt || ''}</textarea></label>
    <button type="button" class="danger">Xóa món</button>`;
  row.querySelector('.danger').onclick = () => row.remove();
  $('items').appendChild(row);
}

function collectItems() {
  return [...document.querySelectorAll('.item')].map((row) => {
    const get = (name) => row.querySelector(`[data-field="${name}"]`).value.trim();
    return {
      name: get('name'), price: get('price'), section: get('section'),
      description: get('description'), image_path: get('image_path') || null,
      image_prompt: get('image_prompt') || null,
    };
  });
}

async function init() {
  try {
    const health = await fetch(`${API}/health`).then((r) => r.json());
    $('serverStatus').textContent = `Server ${health.version}`;
    $('serverStatus').className = 'status ok';
    const data = await fetch(`${API}/api/v1/templates`).then((r) => r.json());
    $('templateSelect').innerHTML = data.templates.map((t) =>
      `<option value="${t.template_id}">${t.name}</option>`).join('');
  } catch (error) {
    $('serverStatus').textContent = 'Server chưa chạy';
    $('serverStatus').className = 'status bad';
  }
}

$('addItem').onclick = () => itemRow();
$('render').onclick = async () => {
  const items = collectItems();
  if (!items.length || items.some((x) => !x.name || !x.price)) {
    $('result').textContent = 'Cần ít nhất một món có tên và giá.';
    return;
  }
  const body = {
    template_path_override: $('templatePath').value.trim() || null,
    title: $('title').value.trim(), subtitle: $('subtitle').value.trim(),
    address: $('address').value.trim(), phone: $('phone').value.trim(),
    sections: [{ name: 'Menu', items }],
    output_dir: $('outputDir').value.trim(), file_stem: $('fileStem').value.trim(),
    generate_missing_images: $('generateImages').checked,
    export_pdf: true, export_png: true, preview_dpi: 150,
  };
  $('result').textContent = 'Đang tạo…';
  try {
    const response = await fetch(`${API}/api/v1/templates/${$('templateSelect').value}/render-menu`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Render thất bại');
    $('result').textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    $('result').textContent = `Lỗi: ${error.message}`;
  }
};

itemRow({ name: 'Cơm tấm sườn', price: '35.000', section: 'Món chính' });
itemRow({ name: 'Bún bò', price: '40.000', section: 'Món chính' });
init();
