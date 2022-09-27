function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
const csrftoken = getCookie('csrftoken');

function fetch_edit_basket(type, p_id) {
    const request = new Request("/eboutic/basket/" + type + "/" + p_id + "/", {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        mode: 'same-origin',
    })
    return fetch(request).then(response => {
        return response.json()
    })
}

function fetch_add(p_id) {
    return fetch_edit_basket("add-product", p_id);
}

function fetch_remove(p_id) {
    return fetch_edit_basket("remove-product", p_id);
}
