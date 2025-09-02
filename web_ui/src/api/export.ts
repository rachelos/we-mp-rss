import http from './http'

export const ExportOPML = () => {
  return http.get<{code: number, data: string}>('/wx/export/mps/opml', {
    params: {
      limit: 1000,
      offset: 0
    }
  })
}

export const ExportMPS = () => {
  return http.get('/wx/export/mps/export', {
    params: { limit: 1000, offset: 0 },
    responseType: 'blob',
  });
};

export const ImportMPS = (formData) => {
  return http.post<{code: number, data: string}>('/wx/export/mps/import', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

export const ExportTags = () => {
  return http.get('/wx/export/tags', {
    params: { limit: 1000, offset: 0 },
    responseType: 'blob',
  });
};

export const ImportTags = (formData: FormData) => {
  return http.post<{code: number, data: string}>('/wx/export/tags/import', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}